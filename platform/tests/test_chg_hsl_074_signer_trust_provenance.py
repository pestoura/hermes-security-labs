from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = ROOT / "platform/assurance/signer_trust_manifest.py"
FIXTURE_TEST_PATH = ROOT / "platform/tests/test_signer_trust_manifest.py"
SCHEMA_PATH = ROOT / "platform/schemas/signer-trust-manifest.schema.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bridge():
    return _load(BRIDGE_PATH, "chg_hsl_074_bridge_provenance")


def _fixtures():
    return _load(FIXTURE_TEST_PATH, "chg_hsl_074_bridge_fixture_helpers")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("attestation_id", "attestation-substituted"),
        ("observed_at", "2026-08-15T21:58:45Z"),
        ("source_evidence_ref", "evidence://signer/substituted-provider-observation.json"),
        ("source_evidence_sha256", "f" * 64),
    ],
)
def test_bridge_refuses_attestation_provenance_not_bound_to_verified_result(
    tmp_path: Path, field: str, replacement: str
) -> None:
    bridge = _bridge()
    fixtures = _fixtures()
    signer_result, attestation, generation, assessment = fixtures._inputs(tmp_path)
    signer_result.update(
        {
            "attestation_id": attestation["attestation_id"],
            "observed_at": attestation["observed_at"],
            "source_evidence_ref": attestation["source_evidence_ref"],
            "source_evidence_sha256": attestation["source_evidence_sha256"],
        }
    )
    attestation[field] = replacement
    with pytest.raises(bridge.SignerTrustManifestError) as exc:
        bridge.build_signer_trust_manifest(
            signer_result=signer_result,
            signer_attestation=attestation,
            trust_generation=generation,
            lifecycle_assessment=assessment,
        )
    assert exc.value.code == "SIGNER_PROVENANCE_MISMATCH"


def test_public_schema_allows_canonical_non_uri_hsm_provider_ref() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = {
        "manifest_id": "stm_" + "a" * 32,
        "schema_version": "signer-trust-manifest/v1",
        "provider_kind": "HSM",
        "provider_ref": "tb1-authorizer-example-slot-a",
        "key_id": "tb1-authorization-example-ed25519",
        "algorithm": "Ed25519",
        "public_key_spki_sha256": "b" * 64,
        "attestation_id": "attestation-001",
        "observed_at": "2026-08-15T21:59:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation.json",
        "source_evidence_sha256": "c" * 64,
        "generation_id": "tsg_" + "d" * 32,
        "generation_sequence": 1,
        "trust_store_sha256": "e" * 64,
        "lifecycle_decision": "ACCEPT_FOR_REVIEW",
        "trust_binding_allowed": False,
        "automatic_activation": False,
        "activation_effect": "NONE",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
    }
    jsonschema.validate(manifest, schema)
