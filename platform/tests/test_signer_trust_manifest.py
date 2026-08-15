from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = ROOT / "platform/assurance/signer_trust_manifest.py"
LIFECYCLE_PATH = ROOT / "platform/roe-contract/trust_store_lifecycle.py"


def _load(path: Path, name: str):
    assert path.exists(), f"{path.name} is not implemented yet"
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _lifecycle():
    return _load(LIFECYCLE_PATH, "chg_hsl_074_trust_store_lifecycle")


def _bridge():
    return _load(BRIDGE_PATH, "chg_hsl_074_signer_trust_manifest")


def _generation_seed(generation: dict) -> dict:
    return {
        "sequence": generation["sequence"],
        "generated_at": generation["generated_at"],
        "previous_generation_id": generation["previous_generation_id"],
        "trust_store_sha256": generation["trust_store_sha256"],
        "keys": generation["keys"],
        "source": generation["source"],
    }


def _recontent_address_generation(generation: dict) -> dict:
    changed = deepcopy(generation)
    encoded = json.dumps(
        _generation_seed(changed), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    changed["generation_id"] = f"tsg_{hashlib.sha256(encoded).hexdigest()[:32]}"
    return changed


def _write_store(path: Path, *, key_id: str = "vault-key-1", state: str = "active", material: bytes = b"spki-one") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": key_id,
                        "algorithm": "Ed25519",
                        "public_key": base64.b64encode(material).decode("ascii"),
                        "state": state,
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


def _inputs(tmp_path: Path):
    lifecycle = _lifecycle()
    material = b"spki-one"
    spki_sha = hashlib.sha256(material).hexdigest()
    store = _write_store(tmp_path / "trust.json", material=material)
    generation = lifecycle.build_generation(
        trust_store_path=store,
        sequence=1,
        generated_at="2026-08-15T21:59:30Z",
        previous_generation_id=None,
    )
    assessment = lifecycle.assess_transition(
        previous=None,
        current=generation,
        evaluated_at="2026-08-15T22:00:00Z",
        max_age_seconds=60,
    )
    signer_result = {
        "signer_attestation_checks_passed": True,
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "findings": [],
        "remaining_evidence": ["LIVE_RUNNER_EFFECT_NOT_RUN"],
        "provider_kind": "VAULT",
        "provider_ref": "vault://hermes/transit/tb1",
        "key_id": "vault-key-1",
        "algorithm": "Ed25519",
        "public_key_spki_sha256": spki_sha,
        "source_evidence_verified": True,
        "attestation_id": "attestation-001",
        "observed_at": "2026-08-15T21:59:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation.json",
        "source_evidence_sha256": "a" * 64,
    }
    attestation = {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "attestation-001",
        "observation_source": "authorized-readonly-observer",
        "observed_at": "2026-08-15T21:59:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation.json",
        "source_evidence_sha256": "a" * 64,
        "provider_kind": "VAULT",
        "provider_ref": "vault://hermes/transit/tb1",
        "key_id": "vault-key-1",
        "algorithm": "Ed25519",
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "public_key_spki_sha256": spki_sha,
    }
    return signer_result, attestation, generation, assessment


def test_builds_deterministic_public_manifest_for_exact_verified_binding(tmp_path: Path) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    first = bridge.build_signer_trust_manifest(
        signer_result=signer_result,
        signer_attestation=attestation,
        trust_generation=generation,
        lifecycle_assessment=assessment,
    )
    second = bridge.build_signer_trust_manifest(
        signer_result=signer_result,
        signer_attestation=attestation,
        trust_generation=generation,
        lifecycle_assessment=assessment,
    )
    assert first == second
    assert first["schema_version"] == "signer-trust-manifest/v1"
    assert first["manifest_id"].startswith("stm_")
    assert first["provider_kind"] == "VAULT"
    assert first["key_id"] == "vault-key-1"
    assert first["algorithm"] == "Ed25519"
    assert first["public_key_spki_sha256"] == signer_result["public_key_spki_sha256"]
    assert first["generation_id"] == generation["generation_id"]
    assert first["trust_store_sha256"] == generation["trust_store_sha256"]
    assert first["source_evidence_ref"] == attestation["source_evidence_ref"]
    assert first["source_evidence_sha256"] == attestation["source_evidence_sha256"]
    assert first["trust_binding_allowed"] is False
    assert first["automatic_activation"] is False
    assert first["activation_effect"] == "NONE"
    assert first["authorization_effect"] == "NONE"
    assert first["execution_authority"] == "NONE"
    assert first["promotion_allowed"] is False
    assert first["runtime_status"] == "NOT_RUN"
    serialized = json.dumps(first, sort_keys=True)
    for forbidden in ("private_key", "token", "password", "credential", "secret"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("signer_result", "signer_attestation_checks_passed"), False, "SIGNER_ATTESTATION_NOT_VERIFIED"),
        (("signer_result", "source_evidence_verified"), False, "SIGNER_SOURCE_EVIDENCE_NOT_VERIFIED"),
        (("signer_result", "provider_kind"), "PKCS11", "SIGNER_CUSTODY_CLASS_NOT_ADMISSIBLE"),
        (("attestation", "observation_status"), "NOT_RUN", "SIGNER_ATTESTATION_NOT_OBSERVED"),
        (("attestation", "key_state"), "revoked", "SIGNER_KEY_NOT_ACTIVE"),
        (("attestation", "signing_enabled"), False, "SIGNER_SIGNING_DISABLED"),
        (("attestation", "private_key_exportable"), True, "SIGNER_PRIVATE_KEY_EXPORTABLE"),
    ],
)
def test_refuses_unverified_or_inadmissible_signer_state(tmp_path: Path, path, value, code: str) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    target = signer_result if path[0] == "signer_result" else attestation
    target[path[1]] = value
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=generation,
            lifecycle_assessment=assessment,
        )
    assert exc.value.code == code


@pytest.mark.parametrize("field", ["provider_kind", "provider_ref", "key_id", "algorithm", "public_key_spki_sha256"])
def test_refuses_identity_mismatch_between_attestation_and_verified_result(tmp_path: Path, field: str) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    attestation[field] = "different" if field != "public_key_spki_sha256" else "b" * 64
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=generation,
            lifecycle_assessment=assessment,
        )
    assert exc.value.code == "SIGNER_IDENTITY_MISMATCH"


def test_refuses_missing_or_noncanonical_source_evidence_binding(tmp_path: Path) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    for field, value in (
        ("source_evidence_ref", "file:///tmp/provider.json"),
        ("source_evidence_sha256", "A" * 64),
    ):
        changed = deepcopy(attestation)
        changed[field] = value
        with pytest.raises(bridge.SignerTrustManifestError) as exc:
            bridge.build_signer_trust_manifest(
                signer_result=signer_result,
                signer_attestation=changed,
                trust_generation=generation,
                lifecycle_assessment=assessment,
            )
        assert exc.value.code == "SIGNER_SOURCE_EVIDENCE_INVALID"


def test_refuses_generation_or_assessment_not_accepted_for_review(tmp_path: Path) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    refused = deepcopy(assessment)
    refused["decision"] = "REFUSE"
    refused["codes"] = ["TRUST_STORE_GENERATION_STALE"]
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=generation,
            lifecycle_assessment=refused,
        )
    assert exc.value.code == "TRUST_GENERATION_NOT_ACCEPTED_FOR_REVIEW"

    wrong_generation = deepcopy(assessment)
    wrong_generation["current_generation_id"] = "tsg_" + "f" * 32
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=generation,
            lifecycle_assessment=wrong_generation,
        )
    assert exc.value.code == "TRUST_GENERATION_ASSESSMENT_MISMATCH"


def test_refuses_assessment_that_claims_activation_or_authority(tmp_path: Path) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)
    for field, value in (
        ("automatic_activation", True),
        ("activation_effect", "ACTIVE"),
        ("authorization_effect", "GRANT"),
        ("execution_authority", "RUNNER"),
    ):
        changed = deepcopy(assessment)
        changed[field] = value
        with pytest.raises(bridge.SignerTrustManifestError) as exc:
            bridge.build_signer_trust_manifest(
                signer_result=signer_result,
                signer_attestation=attestation,
                trust_generation=generation,
                lifecycle_assessment=changed,
            )
        assert exc.value.code == "TRUST_GENERATION_AUTHORITY_INVALID"


def test_refuses_missing_inactive_or_mismatched_key_in_generation(tmp_path: Path) -> None:
    bridge = _bridge()
    signer_result, attestation, generation, assessment = _inputs(tmp_path)

    missing = deepcopy(generation)
    missing["keys"][0]["key_id"] = "other-key"
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=missing,
            lifecycle_assessment=assessment,
        )
    assert exc.value.code == "TRUST_GENERATION_INVALID"

    for field, value, code in (
        ("state", "retired", "TRUST_SIGNER_KEY_NOT_ACTIVE"),
        ("algorithm", "ECDSA-P256-SHA256", "TRUST_SIGNER_ALGORITHM_MISMATCH"),
        ("public_key_sha256", "b" * 64, "TRUST_SIGNER_SPKI_MISMATCH"),
    ):
        changed = deepcopy(generation)
        changed["keys"][0][field] = value
        changed = _recontent_address_generation(changed)
        changed_assessment = deepcopy(assessment)
        changed_assessment["current_generation_id"] = changed["generation_id"]
        with pytest.raises(bridge.SignerTrustManifestError) as exc:
            bridge.build_signer_trust_manifest(
                signer_result=signer_result,
                signer_attestation=attestation,
                trust_generation=changed,
                lifecycle_assessment=changed_assessment,
            )
        assert exc.value.code == code


def test_module_has_no_trust_installation_provider_network_or_signing_behavior() -> None:
    bridge = _bridge()
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "bind_trust_store(",
        "requests.",
        "httpx.",
        "socket.",
        "subprocess.",
        "Ed25519PrivateKey",
        "ECPrivateKey",
        "hvac",
        "boto3",
        "pkcs11",
    ):
        assert forbidden not in source
    assert bridge.PROMOTION_ALLOWED is False
    assert bridge.RUNTIME_STATUS == "NOT_RUN"
