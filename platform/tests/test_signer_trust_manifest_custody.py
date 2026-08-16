from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
EVIDENCE = ROOT / "platform" / "evidence-plane"
ROE = ROOT / "platform" / "roe-contract"
CUSTODY_PATH = EVIDENCE / "signer_trust_manifest_custody.py"
POLICY_PATH = EVIDENCE / "signer-trust-manifest-custody-policy.yaml"
MANIFEST_PATH = ASSURANCE / "signer_trust_manifest.py"
LIFECYCLE_PATH = ROE / "trust_store_lifecycle.py"
STORE_PATH = EVIDENCE / "local_store.py"
VERIFIER_PATH = EVIDENCE / "local_evidence_verifier.py"


def _load(path: Path, name: str) -> Any:
    assert path.exists(), f"{path.name} is not implemented yet"
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _custody():
    return _load(CUSTODY_PATH, "chg_hsl_077_signer_trust_manifest_custody")


def _manifest_module():
    return _load(MANIFEST_PATH, "chg_hsl_077_signer_trust_manifest")


def _lifecycle():
    return _load(LIFECYCLE_PATH, "chg_hsl_077_trust_store_lifecycle")


def _store_module():
    return _load(STORE_PATH, "chg_hsl_077_local_store")


def _verifier_module():
    return _load(VERIFIER_PATH, "chg_hsl_077_local_evidence_verifier")


def _write_trust_store(path: Path, material: bytes = b"spki-chg-077") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": "vault-key-077",
                        "algorithm": "Ed25519",
                        "public_key": base64.b64encode(material).decode("ascii"),
                        "state": "active",
                        "not_before": "2026-08-01T00:00:00Z",
                        "not_after": "2027-08-01T00:00:00Z",
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _manifest(tmp_path: Path) -> dict[str, Any]:
    lifecycle = _lifecycle()
    composer = _manifest_module()
    material = b"spki-chg-077"
    spki_sha = hashlib.sha256(material).hexdigest()
    trust_store = _write_trust_store(tmp_path / "trust.json", material)
    generation = lifecycle.build_generation(
        trust_store_path=trust_store,
        sequence=1,
        generated_at="2026-08-16T02:55:30Z",
        previous_generation_id=None,
    )
    assessment = lifecycle.assess_transition(
        previous=None,
        current=generation,
        evaluated_at="2026-08-16T02:56:00Z",
        max_age_seconds=60,
    )
    signer_result = {
        "signer_attestation_checks_passed": True,
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "findings": [],
        "remaining_evidence": ["LIVE_RUNNER_EFFECT_NOT_RUN"],
        "provider_kind": "VAULT",
        "provider_ref": "vault-target-deferred",
        "key_id": "vault-key-077",
        "algorithm": "Ed25519",
        "public_key_spki_sha256": spki_sha,
        "source_evidence_verified": True,
        "attestation_id": "attestation-077",
        "observed_at": "2026-08-16T02:55:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation-077.json",
        "source_evidence_sha256": "a" * 64,
    }
    attestation = {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "attestation-077",
        "observation_source": "authorized-readonly-observer",
        "observed_at": "2026-08-16T02:55:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation-077.json",
        "source_evidence_sha256": "a" * 64,
        "provider_kind": "VAULT",
        "provider_ref": "vault-target-deferred",
        "key_id": "vault-key-077",
        "algorithm": "Ed25519",
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "public_key_spki_sha256": spki_sha,
    }
    return composer.build_signer_trust_manifest(
        signer_result=signer_result,
        signer_attestation=attestation,
        trust_generation=generation,
        lifecycle_assessment=assessment,
    )


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-077",
        "run_id": "run-077",
        "step_id": "trust-manifest-077",
        "attempt_id": "attempt-077",
    }


def _enabled_policy() -> dict[str, Any]:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return policy


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def test_canonical_policy_is_disabled_and_fail_closed(tmp_path: Path) -> None:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    assert policy == {
        "schema_version": "1.0",
        "policy_id": "hexor.signer.trust_manifest.custody",
        "state": "DISABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "custody": {
            "evidence_plane_projection": "required",
            "classification": "restricted",
            "retention_policy_id": "default-30d",
            "retention_days": 30,
            "include_private_key": False,
            "include_raw_signing_payload": False,
            "include_raw_signature": False,
            "install_trust": False,
        },
    }
    assert custody.validate_policy(policy) == []

    class TouchStore:
        touched = False

        def put(self, record, payload):  # noqa: ANN001
            self.touched = True
            raise AssertionError("disabled custody must not touch the store")

        def verify(self, evidence_id):  # noqa: ANN001
            self.touched = True
            raise AssertionError("disabled custody must not touch the store")

    store = TouchStore()
    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        custody.SignerTrustManifestCustody(policy).persist(
            _manifest(tmp_path),
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=store,
        )
    assert exc.value.code == "CUSTODY_DISABLED"
    assert store.touched is False


def test_manifest_identity_is_recomputed_before_any_write(tmp_path: Path) -> None:
    custody = _custody()
    manifest = _manifest(tmp_path)
    body = dict(manifest)
    supplied_id = body.pop("manifest_id")
    expected_id = "stm_" + hashlib.sha256(_canonical_bytes(body)).hexdigest()[:32]
    assert supplied_id == expected_id

    changed = deepcopy(manifest)
    changed["provider_ref"] = "different-but-schema-valid-provider-ref"

    class NoWriteStore:
        touched = False

        def put(self, record, payload):  # noqa: ANN001
            self.touched = True
            raise AssertionError("identity mismatch must be refused before write")

        def verify(self, evidence_id):  # noqa: ANN001
            self.touched = True
            raise AssertionError("identity mismatch must be refused before verification")

    store = NoWriteStore()
    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        custody.SignerTrustManifestCustody(_enabled_policy()).persist(
            changed,
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=store,
        )
    assert exc.value.code == "MANIFEST_ID_MISMATCH"
    assert store.touched is False


def test_projects_exact_public_manifest_to_existing_evidence_plane(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    manifest = _manifest(tmp_path)
    result = custody.SignerTrustManifestCustody(_enabled_policy()).persist(
        manifest,
        correlation=_correlation(),
        recorded_at="2026-08-16T03:00:00Z",
        evidence_store=store,
    )

    expected_payload = _canonical_bytes(manifest)
    expected_sha = hashlib.sha256(expected_payload).hexdigest()
    assert result.manifest_id == manifest["manifest_id"]
    assert result.evidence_ref == f"evidence://{result.evidence_id}"
    assert result.payload_sha256 == expected_sha
    assert result.classification == "restricted"
    assert store.verify(result.evidence_id) is True

    record = store.get_record(result.evidence_id)
    assert record["classification"] == "restricted"
    assert record["correlation"] == _correlation()
    assert record["origin"]["producer"] == "signer-trust-manifest-custody-v1"
    assert record["origin"]["operation"] == "signer.trust_manifest.custody"
    assert record["origin"]["protocol_version"] == "signer-trust-manifest/v1"
    assert record["content"]["sha256"] == expected_sha
    assert record["content"]["size"] == len(expected_payload)
    assert record["content"]["media_type"] == "application/json"
    assert record["content"]["storage_ref"] == (
        f"evidence://signer-trust-manifest/{expected_sha}"
    )
    assert record["retention"]["policy_id"] == "default-30d"

    object_path = store.objects / expected_sha[:2] / expected_sha
    assert object_path.read_bytes() == expected_payload
    assert json.loads(object_path.read_text(encoding="utf-8")) == manifest


def test_local_evidence_verifier_binds_exact_ref_and_digest(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    result = custody.SignerTrustManifestCustody(_enabled_policy()).persist(
        _manifest(tmp_path),
        correlation=_correlation(),
        recorded_at="2026-08-16T03:00:00Z",
        evidence_store=store,
    )
    verifier = _verifier_module().LocalEvidenceVerifier(store)
    record = store.get_record(result.evidence_id)
    storage_ref = record["content"]["storage_ref"]

    assert verifier.verify(result.evidence_ref, result.payload_sha256) is True
    assert verifier.verify(result.evidence_id, result.payload_sha256) is True
    assert verifier.verify(storage_ref, result.payload_sha256) is True
    assert verifier.verify(result.evidence_ref, "0" * 64) is False
    assert verifier.verify("evidence://ev_" + "f" * 32, result.payload_sha256) is False

    object_path = store.objects / result.payload_sha256[:2] / result.payload_sha256
    object_path.write_bytes(b"tampered")
    assert verifier.verify(result.evidence_ref, result.payload_sha256) is False
    assert verifier.verify(storage_ref, result.payload_sha256) is False


def test_identical_persistence_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    bridge = custody.SignerTrustManifestCustody(_enabled_policy())
    manifest = _manifest(tmp_path)
    kwargs = {
        "correlation": _correlation(),
        "recorded_at": "2026-08-16T03:00:00Z",
        "evidence_store": store,
    }
    first = bridge.persist(manifest, **kwargs)
    second = bridge.persist(manifest, **kwargs)
    assert second == first
    assert len(list(store.records.glob("ev_*.json"))) == 1
    assert len(list((store.objects / first.payload_sha256[:2]).glob(first.payload_sha256))) == 1


def test_extra_or_secret_bearing_manifest_is_refused_before_write(tmp_path: Path) -> None:
    custody = _custody()
    manifest = deepcopy(_manifest(tmp_path))
    manifest["token"] = "forbidden"

    class NoWriteStore:
        touched = False

        def put(self, record, payload):  # noqa: ANN001
            self.touched = True
            raise AssertionError("invalid manifest must not be written")

        def verify(self, evidence_id):  # noqa: ANN001
            self.touched = True
            raise AssertionError("invalid manifest must not be verified")

    store = NoWriteStore()
    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        custody.SignerTrustManifestCustody(_enabled_policy()).persist(
            manifest,
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=store,
        )
    assert exc.value.code == "MANIFEST_INVALID"
    assert store.touched is False


def test_store_contract_and_backend_failures_fail_closed_without_leakage(tmp_path: Path) -> None:
    custody = _custody()
    bridge = custody.SignerTrustManifestCustody(_enabled_policy())
    manifest = _manifest(tmp_path)

    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        bridge.persist(
            manifest,
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=None,
        )
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"

    class FailingStore:
        def put(self, record, payload):  # noqa: ANN001
            raise RuntimeError("/sensitive/provider/path")

        def verify(self, evidence_id):  # noqa: ANN001
            return True

    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        bridge.persist(
            manifest,
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=FailingStore(),
        )
    assert exc.value.code == "EVIDENCE_PROJECTION_FAILED"
    assert "/sensitive/provider/path" not in str(exc.value)

    class NonVerifyingStore:
        def put(self, record, payload):  # noqa: ANN001
            return record["evidence_id"]

        def verify(self, evidence_id):  # noqa: ANN001
            return False

    with pytest.raises(custody.SignerTrustManifestCustodyError) as exc:
        bridge.persist(
            manifest,
            correlation=_correlation(),
            recorded_at="2026-08-16T03:00:00Z",
            evidence_store=NonVerifyingStore(),
        )
    assert exc.value.code == "EVIDENCE_VERIFICATION_FAILED"


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda p: p.update(state="BROKEN"), "state must be DISABLED or ENABLED"),
        (lambda p: p.update(default="allow"), "default must be deny"),
        (lambda p: p.update(runtime_status="READY"), "runtime_status must remain NOT_RUN"),
        (lambda p: p.update(execution_authority="runner"), "must never claim execution authority"),
        (lambda p: p["custody"].update(classification="summary"), "classification must be restricted"),
        (lambda p: p["custody"].update(retention_policy_id="forever"), "retention_policy_id"),
        (lambda p: p["custody"].update(retention_days=31), "retention_days must be 30"),
        (lambda p: p["custody"].update(include_private_key=True), "private key"),
        (lambda p: p["custody"].update(include_raw_signing_payload=True), "raw signing payload"),
        (lambda p: p["custody"].update(include_raw_signature=True), "raw signature"),
        (lambda p: p["custody"].update(install_trust=True), "trust installation"),
        (lambda p: p["custody"].update(extra=True), "exact fields"),
    ],
)
def test_policy_mutations_fail_validation(mutator, expected: str) -> None:  # noqa: ANN001
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    mutator(policy)
    assert any(expected in finding for finding in custody.validate_policy(policy))


def test_custody_source_has_no_provider_runtime_trust_install_or_parallel_integrity_primitives() -> None:
    _custody()
    source = CUSTODY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)

    assert not imported & {
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "boto3",
        "hvac",
        "pkcs11",
        "docker",
    }
    assert "LocalEvidenceStore" not in called_names
    assert "LocalEvidenceVerifier" not in called_names
    assert "EvidenceChain" not in called_names
    assert "AuditSink" not in called_names
    assert "bind_trust_store" not in called_names
    assert "evidence_store.put(" in source
    assert "evidence_store.verify(" in source
