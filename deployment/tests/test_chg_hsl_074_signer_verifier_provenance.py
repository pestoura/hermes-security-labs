from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deployment/runtime-promotion/runtime_signer_attestation.py"
DEPLOYMENT_PATH = ROOT / "deployment/runtime-promotion/templates/tb1-authorization-deployment-descriptor.example.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("chg_hsl_074_runtime_signer_attestation", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AcceptExactEvidence:
    def __init__(self, ref: str, sha256: str) -> None:
        self.ref = ref
        self.sha256 = sha256

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        return evidence_ref == self.ref and sha256 == self.sha256


def _fresh_observed_attestation(module, deployment: dict) -> dict:
    signer = deployment["signer"]
    observed_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "chg-hsl-074-provenance-fixture",
        "observation_source": "authorized-readonly-observer",
        "observed_at": observed_at,
        "source_evidence_ref": "evidence://signer/chg-hsl-074-provider.json",
        "source_evidence_sha256": "7" * 64,
        "provider_kind": signer["provider_kind"],
        "provider_ref": signer["provider_ref"],
        "key_id": signer["key_id"],
        "algorithm": signer["algorithm"],
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "public_key_spki_sha256": module._approved_public_key_digest(deployment),
    }


def test_verified_result_binds_exact_public_attestation_provenance() -> None:
    module = _load()
    deployment = module.load_deployment_descriptor(DEPLOYMENT_PATH)
    attestation = _fresh_observed_attestation(module, deployment)
    result = module.verify_signer_attestation(
        deployment,
        attestation,
        evidence_verifier=AcceptExactEvidence(
            attestation["source_evidence_ref"], attestation["source_evidence_sha256"]
        ),
    )
    assert result.signer_attestation_checks_passed is True
    rendered = result.as_dict()
    assert rendered["attestation_id"] == attestation["attestation_id"]
    assert rendered["observed_at"] == attestation["observed_at"]
    assert rendered["source_evidence_ref"] == attestation["source_evidence_ref"]
    assert rendered["source_evidence_sha256"] == attestation["source_evidence_sha256"]
    assert rendered["source_evidence_verified"] is True
