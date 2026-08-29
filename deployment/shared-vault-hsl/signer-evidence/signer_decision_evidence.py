#!/usr/bin/env python3
"""Assemble sanitized shared-Vault evidence for the #403 human decision gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
BUNDLE_SCHEMA = HERE / "decision-evidence-bundle.schema.json"
R1_R8_SCHEMA = HERE / "r1-r8-review.schema.json"
PROVIDER_MODULE = HERE / "vault_provider_observation.py"
ATTESTATION_MODULE = ROOT / "deployment/runtime-promotion/runtime_signer_attestation.py"
TRUST_LIFECYCLE_MODULE = ROOT / "platform/roe-contract/trust_store_lifecycle.py"
TRUST_MANIFEST_MODULE = ROOT / "platform/assurance/signer_trust_manifest.py"
BASELINE_PATH = ROOT / "platform/assurance/signer-baseline.yaml"
TRUST_MANIFEST_SCHEMA = ROOT / "platform/schemas/signer-trust-manifest.schema.json"
ATTESTATION_SCHEMA = ROOT / "deployment/runtime-promotion/tb1-signer-attestation.schema.json"
BUNDLE_SCHEMA_VERSION = "hsl.signer-decision-evidence-bundle/v1"
R1_R8_SCHEMA_VERSION = "hsl.signer-r1-r8-review/v1"

_FORBIDDEN_FIELDS = frozenset(
    {
        "token",
        "client" + "_token",
        "secret",
        "secret" + "_id",
        "role" + "_id",
        "wrapping" + "_token",
        "password",
        "passphrase",
        "credential",
        "credentials",
        "private_key",
        "api_key",
    }
)


class DecisionEvidenceError(ValueError):
    """Stable fail-closed signer decision evidence error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _load_module(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DecisionEvidenceError("DECISION_EVIDENCE_DEPENDENCY_UNAVAILABLE", path.name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _secret_paths(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _normalized_key(key) in _FORBIDDEN_FIELDS:
                findings.append(child)
            findings.extend(_secret_paths(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_secret_paths(nested, f"{path}[{index}]"))
    return findings


def _validate_schema(document: Mapping[str, Any], schema_path: Path, *, code: str) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise DecisionEvidenceError(code, f"schema unavailable: {schema_path.name}") from exc
    validator_class = jsonschema.validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise DecisionEvidenceError(code, f"{location}: {first.message}")


def _artifact(kind: str, document: Mapping[str, Any]) -> tuple[dict[str, str], bytes]:
    payload = _canonical_bytes(document)
    digest = _sha256(payload)
    pointer = {
        "ref": f"evidence://signer/{kind}/{digest}.json",
        "sha256": digest,
        "file": f"{kind}-{digest[:16]}.json",
    }
    return pointer, payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise DecisionEvidenceError(
                "DECISION_EVIDENCE_IMMUTABLE_PATH_CONFLICT", path.name
            )
        return
    with os.fdopen(fd, "wb", closefd=True) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _outside_repository(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return resolved
    raise DecisionEvidenceError(
        "DECISION_EVIDENCE_REPOSITORY_WRITE_REFUSED",
        "assembly output must be staged outside the repository",
    )


class _ExactArtifactVerifier:
    """Verify one exact in-memory evidence artifact by canonical ref and digest."""

    def __init__(self, ref: str, payload: bytes) -> None:
        self._ref = ref
        self._sha256 = _sha256(payload)

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        return evidence_ref == self._ref and sha256 == self._sha256


provider_observation = _load_module(
    "hsl_chg105_provider_observation", PROVIDER_MODULE
)
runtime_signer_attestation = _load_module(
    "hsl_chg105_runtime_signer_attestation", ATTESTATION_MODULE
)
trust_store_lifecycle = _load_module(
    "hsl_chg105_trust_store_lifecycle", TRUST_LIFECYCLE_MODULE
)
signer_trust_manifest = _load_module(
    "hsl_chg105_signer_trust_manifest", TRUST_MANIFEST_MODULE
)


def _load_baseline() -> Mapping[str, Any]:
    try:
        document = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        raise DecisionEvidenceError("R1_R8_BASELINE_INVALID", "signer baseline unavailable") from exc
    if not isinstance(document, Mapping):
        raise DecisionEvidenceError("R1_R8_BASELINE_INVALID", "signer baseline is invalid")
    baseline = document.get("signer_baseline")
    if not isinstance(baseline, Mapping):
        raise DecisionEvidenceError("R1_R8_BASELINE_INVALID", "signer baseline section missing")
    if baseline.get("accepted") is not True or baseline.get("provider_neutral") is not True:
        raise DecisionEvidenceError("R1_R8_BASELINE_INVALID", "signer baseline is not accepted")
    if baseline.get("supplier_selection") != "NO_SELECTION":
        raise DecisionEvidenceError("R1_R8_BASELINE_INVALID", "supplier selection already changed")
    return baseline


def _public_trust_store(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "purpose": "tb1-authorization",
        "keys": [
            {
                "key_id": observation["key_id"],
                "algorithm": observation["algorithm"],
                "state": "active",
                "purpose": "tb1-authorization",
                "public_key": observation["public_key_spki_b64"],
            }
        ],
    }


def _deployment_descriptor(
    observation: Mapping[str, Any], trust_store: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "runtime_status": "NOT_RUN",
        "authority": "hermes-control-plane",
        "domain": "hex0r.tb1.authorization.v1",
        "purpose": "tb1-authorization",
        "signer": {
            "provider_kind": "VAULT",
            "provider_ref": observation["provider_ref"],
            "key_id": observation["key_id"],
            "algorithm": observation["algorithm"],
            "private_key_local": False,
        },
        "trust_store": {
            "install_path": "/run/hexor/runner/authorization-trust-store.json",
            "document": dict(trust_store),
        },
    }


def _signer_attestation(
    observation: Mapping[str, Any], capability: Mapping[str, str]
) -> dict[str, Any]:
    seed = {
        "provider_ref": observation["provider_ref"],
        "key_id": observation["key_id"],
        "observed_at": observation["observed_at"],
        "capability_sha256": capability["sha256"],
    }
    attestation_id = f"hsl-vault-{_sha256(_canonical_bytes(seed))[:24]}"
    return {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": attestation_id,
        "observation_source": "shared-vault-authorized-public-metadata",
        "observed_at": observation["observed_at"],
        "source_evidence_ref": capability["ref"],
        "source_evidence_sha256": capability["sha256"],
        "provider_kind": "VAULT",
        "provider_ref": observation["provider_ref"],
        "key_id": observation["key_id"],
        "algorithm": observation["algorithm"],
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "public_key_spki_sha256": observation["public_key_spki_sha256"],
    }


def _require_baseline_controls(baseline: Mapping[str, Any]) -> None:
    required = (
        "requires_external_signer",
        "requires_non_exportable_private_key",
        "requires_purpose_bound_key_identity",
        "requires_explicit_trust_store",
        "requires_trust_store_digest_binding",
        "requires_provider_observation_attestation",
        "requires_signing_enabled_active",
        "requires_auditability",
        "requires_revocation_rotation_fail_closed",
        "requires_cost_proportional_bring_up",
        "requires_evidence_separation",
    )
    missing = [name for name in required if baseline.get(name) is not True]
    if missing:
        raise DecisionEvidenceError(
            "R1_R8_BASELINE_INVALID", "required baseline controls missing: " + ", ".join(missing)
        )


def _build_r1_r8_review(
    observation: Mapping[str, Any],
    *,
    evaluated_at: str,
    capability: Mapping[str, str],
    attestation: Mapping[str, str],
    public_store: Mapping[str, str],
    trust_manifest: Mapping[str, str],
    signer_result: Mapping[str, Any],
    lifecycle_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = _load_baseline()
    _require_baseline_controls(baseline)
    if signer_result.get("signer_attestation_checks_passed") is not True:
        raise DecisionEvidenceError("R1_R8_REVIEW_FAILED", "signer attestation did not pass")
    if lifecycle_assessment.get("decision") != "ACCEPT_FOR_REVIEW":
        raise DecisionEvidenceError("R1_R8_REVIEW_FAILED", "trust generation was refused")

    audit_ref = observation["audit_evidence"]["ref"]
    bootstrap_ref = observation["bootstrap_evidence"]["ref"]
    requirements = [
        {"id": "R1", "result": "PASS", "basis": "Vault Transit signing is service-mediated and the observed private key is non-exportable with plaintext backup disabled.", "evidence_refs": [capability["ref"], attestation["ref"]]},
        {"id": "R2", "result": "PASS", "basis": "Provider, versioned key identity, Ed25519 algorithm, TB1 domain and purpose are explicitly bound by the verified descriptor.", "evidence_refs": [attestation["ref"], trust_manifest["ref"]]},
        {"id": "R3", "result": "PASS", "basis": "The explicit trust-store snapshot contains public verification material only and its exact SPKI and content digest are bound to the signer manifest.", "evidence_refs": [public_store["ref"], trust_manifest["ref"]]},
        {"id": "R4", "result": "PASS", "basis": "The live capability observation records active signing plus a successful bounded sign/verify challenge; canonical adapter failure semantics remain fail-closed.", "evidence_refs": [capability["ref"], attestation["ref"]]},
        {"id": "R5", "result": "PASS", "basis": "A sanitized provider audit attribution result is required and was observed for the bounded signing capability check.", "evidence_refs": [capability["ref"], audit_ref]},
        {"id": "R6", "result": "PASS", "basis": "The accepted trust-store lifecycle uses content-addressed generations and fail-closed key-state transitions without runtime-code mutation.", "evidence_refs": [public_store["ref"], trust_manifest["ref"]]},
        {"id": "R7", "result": "PASS", "basis": "The shared software Vault lane is reproducible from non-secret descriptors and the hardened consumer, without a hardware procurement dependency for LAB_L1.", "evidence_refs": [capability["ref"], bootstrap_ref]},
        {"id": "R8", "result": "PASS", "basis": "Generated decision evidence contains no secret/private material and grants no authorization, trust, execution or promotion authority.", "evidence_refs": [capability["ref"], attestation["ref"], trust_manifest["ref"]]},
    ]
    body: dict[str, Any] = {
        "schema_version": R1_R8_SCHEMA_VERSION,
        "evaluated_at": evaluated_at,
        "custody_class": "VAULT",
        "provider_ref": observation["provider_ref"],
        "key_id": observation["key_id"],
        "requirements": requirements,
        "all_passed": True,
        "trust_binding_allowed": False,
        "promotion_allowed": False,
        "execution_authority": "NONE",
        "runtime_status": "NOT_RUN",
    }
    review_id = f"r1r8_{_sha256(_canonical_bytes(body))[:32]}"
    review = {"review_id": review_id, **body}
    _validate_schema(review, R1_R8_SCHEMA, code="R1_R8_REVIEW_SCHEMA_INVALID")
    return review


def _decision_ref(kind: str, pointer: Mapping[str, str]) -> dict[str, str]:
    return {
        "kind": kind,
        "ref": pointer["ref"],
        "sha256": pointer["sha256"],
    }


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def assemble_decision_evidence(
    observation: Mapping[str, Any],
    *,
    output_dir: Path,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble and persist a sanitized no-authority evidence bundle outside Git."""

    if not isinstance(observation, Mapping):
        raise DecisionEvidenceError("PROVIDER_OBSERVATION_INVALID", "observation must be an object")
    secret_paths = _secret_paths(observation)
    if secret_paths:
        raise DecisionEvidenceError(
            "DECISION_EVIDENCE_SECRET_MATERIAL_REFUSED",
            "secret/private material field refused: " + ", ".join(secret_paths),
        )
    try:
        provider_observation.validate_provider_observation(observation)
    except Exception as exc:
        raise DecisionEvidenceError("PROVIDER_OBSERVATION_INVALID", str(exc)) from exc
    if observation.get("state") != "OBSERVED":
        raise DecisionEvidenceError("PROVIDER_OBSERVATION_NOT_OBSERVED", "live provider observation required")

    target = _outside_repository(Path(output_dir))
    evaluated_at = evaluated_at or _now_rfc3339()
    capability_ptr, capability_payload = _artifact("vault-capability", observation)
    public_store_doc = _public_trust_store(observation)
    public_store_ptr, public_store_payload = _artifact("public-trust-store", public_store_doc)

    descriptor = _deployment_descriptor(observation, public_store_doc)
    attestation_doc = _signer_attestation(observation, capability_ptr)
    _validate_schema(
        attestation_doc, ATTESTATION_SCHEMA, code="SIGNER_ATTESTATION_SCHEMA_INVALID"
    )
    attestation_ptr, attestation_payload = _artifact("signer-attestation", attestation_doc)
    verifier = _ExactArtifactVerifier(capability_ptr["ref"], capability_payload)
    try:
        signer_result = runtime_signer_attestation.verify_signer_attestation(
            descriptor,
            attestation_doc,
            evidence_verifier=verifier,
        )
    except Exception as exc:
        raise DecisionEvidenceError("SIGNER_ATTESTATION_NOT_VERIFIED", str(exc)) from exc
    if signer_result.signer_attestation_checks_passed is not True:
        raise DecisionEvidenceError(
            "SIGNER_ATTESTATION_NOT_VERIFIED",
            "; ".join(signer_result.findings) or "signer attestation failed closed",
        )

    with tempfile.TemporaryDirectory(prefix="hsl-signer-decision-") as temp_dir:
        trust_path = Path(temp_dir) / "authorization-trust-store.json"
        trust_path.write_bytes(public_store_payload)
        try:
            generation = trust_store_lifecycle.build_generation(
                trust_store_path=trust_path,
                sequence=1,
                generated_at=str(observation["observed_at"]),
                previous_generation_id=None,
            )
            lifecycle_assessment = trust_store_lifecycle.assess_transition(
                previous=None,
                current=generation,
                evaluated_at=evaluated_at,
                max_age_seconds=300,
            )
        except Exception as exc:
            raise DecisionEvidenceError("TRUST_GENERATION_NOT_ACCEPTED", str(exc)) from exc
    if lifecycle_assessment.get("decision") != "ACCEPT_FOR_REVIEW":
        raise DecisionEvidenceError(
            "TRUST_GENERATION_NOT_ACCEPTED",
            "; ".join(lifecycle_assessment.get("codes") or ["trust generation refused"]),
        )

    try:
        trust_manifest_doc = signer_trust_manifest.build_signer_trust_manifest(
            signer_result=signer_result.as_dict(),
            signer_attestation=attestation_doc,
            trust_generation=generation,
            lifecycle_assessment=lifecycle_assessment,
        )
    except Exception as exc:
        raise DecisionEvidenceError("TRUST_MANIFEST_NOT_VERIFIED", str(exc)) from exc
    _validate_schema(
        trust_manifest_doc, TRUST_MANIFEST_SCHEMA, code="TRUST_MANIFEST_SCHEMA_INVALID"
    )
    trust_manifest_ptr, trust_manifest_payload = _artifact(
        "signer-trust-manifest", trust_manifest_doc
    )

    review_doc = _build_r1_r8_review(
        observation,
        evaluated_at=evaluated_at,
        capability=capability_ptr,
        attestation=attestation_ptr,
        public_store=public_store_ptr,
        trust_manifest=trust_manifest_ptr,
        signer_result=signer_result.as_dict(),
        lifecycle_assessment=lifecycle_assessment,
    )
    review_ptr, review_payload = _artifact("r1-r8-review", review_doc)

    artifacts = {
        "capability_evidence": capability_ptr,
        "signer_attestation": attestation_ptr,
        "public_trust_store": public_store_ptr,
        "trust_store_manifest": trust_manifest_ptr,
        "r1_r8_review": review_ptr,
    }
    decision_refs = [
        _decision_ref("capability_evidence", capability_ptr),
        _decision_ref("signer_attestation", attestation_ptr),
        _decision_ref("trust_store_manifest", trust_manifest_ptr),
        _decision_ref("r1_r8_review", review_ptr),
    ]
    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "state": "READY_FOR_HUMAN_DECISION",
        "custody_class": "VAULT",
        "evaluated_at": evaluated_at,
        "artifacts": artifacts,
        "decision_evidence_refs": decision_refs,
        "bundle_file": "decision-evidence-bundle.json",
        "signer_decision_effect": "NONE",
        "supplier_selection_effect": "NONE",
        "trust_binding_allowed": False,
        "promotion_allowed": False,
        "execution_authority": "NONE",
        "runtime_status": "NOT_RUN",
    }
    _validate_schema(bundle, BUNDLE_SCHEMA, code="DECISION_EVIDENCE_BUNDLE_SCHEMA_INVALID")

    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    for pointer, payload in (
        (capability_ptr, capability_payload),
        (attestation_ptr, attestation_payload),
        (public_store_ptr, public_store_payload),
        (trust_manifest_ptr, trust_manifest_payload),
        (review_ptr, review_payload),
    ):
        _atomic_write(target / pointer["file"], payload)
    _atomic_write(target / bundle["bundle_file"], _canonical_bytes(bundle))
    if not verify_decision_evidence_bundle(bundle, target):
        raise DecisionEvidenceError("DECISION_EVIDENCE_BUNDLE_VERIFY_FAILED", "written bundle failed verification")
    return bundle


def verify_decision_evidence_bundle(
    bundle: Mapping[str, Any], root: Path
) -> bool:
    """Verify artifact integrity and cross-binding without re-running live freshness."""

    try:
        if not isinstance(bundle, Mapping):
            return False
        _validate_schema(bundle, BUNDLE_SCHEMA, code="DECISION_EVIDENCE_BUNDLE_SCHEMA_INVALID")
        root = Path(root).expanduser().resolve()
        artifacts = bundle["artifacts"]
        documents: dict[str, Mapping[str, Any]] = {}
        for name, pointer in artifacts.items():
            path = root / pointer["file"]
            payload = path.read_bytes()
            if _sha256(payload) != pointer["sha256"]:
                return False
            if not pointer["ref"].endswith(f"/{pointer['sha256']}.json"):
                return False
            document = json.loads(payload)
            if not isinstance(document, Mapping) or _secret_paths(document):
                return False
            documents[name] = document

        if (root / bundle["bundle_file"]).read_bytes() != _canonical_bytes(bundle):
            return False
        provider_observation.validate_provider_observation(documents["capability_evidence"])
        _validate_schema(
            documents["signer_attestation"],
            ATTESTATION_SCHEMA,
            code="SIGNER_ATTESTATION_SCHEMA_INVALID",
        )
        _validate_schema(
            documents["trust_store_manifest"],
            TRUST_MANIFEST_SCHEMA,
            code="TRUST_MANIFEST_SCHEMA_INVALID",
        )
        _validate_schema(
            documents["r1_r8_review"],
            R1_R8_SCHEMA,
            code="R1_R8_REVIEW_SCHEMA_INVALID",
        )

        capability = artifacts["capability_evidence"]
        attestation = documents["signer_attestation"]
        trust_manifest = documents["trust_store_manifest"]
        review = documents["r1_r8_review"]
        if attestation["source_evidence_ref"] != capability["ref"]:
            return False
        if attestation["source_evidence_sha256"] != capability["sha256"]:
            return False
        if trust_manifest["trust_store_sha256"] != artifacts["public_trust_store"]["sha256"]:
            return False
        if trust_manifest["key_id"] != attestation["key_id"]:
            return False
        if trust_manifest["public_key_spki_sha256"] != attestation["public_key_spki_sha256"]:
            return False
        if review["key_id"] != attestation["key_id"] or review["all_passed"] is not True:
            return False

        expected = {
            "capability_evidence": artifacts["capability_evidence"],
            "signer_attestation": artifacts["signer_attestation"],
            "trust_store_manifest": artifacts["trust_store_manifest"],
            "r1_r8_review": artifacts["r1_r8_review"],
        }
        seen: set[str] = set()
        for entry in bundle["decision_evidence_refs"]:
            kind = entry["kind"]
            if kind in seen or kind not in expected:
                return False
            seen.add(kind)
            pointer = expected[kind]
            if entry["ref"] != pointer["ref"] or entry["sha256"] != pointer["sha256"]:
                return False
        return seen == set(expected)
    except Exception:
        return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser("assemble")
    assemble.add_argument("--observation", type=Path, required=True)
    assemble.add_argument("--output-dir", type=Path, required=True)
    assemble.add_argument("--evaluated-at")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--root", type=Path, required=True)
    return parser


def _load_mapping_file(path: Path) -> Mapping[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        raise DecisionEvidenceError("DECISION_EVIDENCE_INPUT_INVALID", path.name) from exc
    if not isinstance(document, Mapping):
        raise DecisionEvidenceError("DECISION_EVIDENCE_INPUT_INVALID", path.name)
    return document


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "assemble":
            bundle = assemble_decision_evidence(
                _load_mapping_file(args.observation),
                output_dir=args.output_dir,
                evaluated_at=args.evaluated_at,
            )
            print(json.dumps(bundle, sort_keys=True, separators=(",", ":")))
            return 0

        bundle = _load_mapping_file(args.bundle)
        if verify_decision_evidence_bundle(bundle, args.root):
            print("BUNDLE_VERIFY_PASS")
            return 0
        print("BUNDLE_VERIFY_FAIL", file=sys.stderr)
        return 2
    except DecisionEvidenceError as exc:
        print(f"FAIL {exc.code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
