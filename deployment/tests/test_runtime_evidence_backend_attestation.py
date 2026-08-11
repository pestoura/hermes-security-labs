from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_evidence_backend_attestation.py"
)
ATTESTATION_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "evidence-backend-attestation.example.yaml"
)
SOURCE_REF = "evidence://runner-live/backend/provider-metadata/fixture.json"
SOURCE_SHA = "6" * 64


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backend = _load("runtime_evidence_backend_attestation_test", MODULE_PATH)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _observed_attestation() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "evidence-production-backend-fixture",
        "observation_source": "provider-read-only-metadata",
        "observed_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=10)),
        "source_evidence_ref": SOURCE_REF,
        "source_evidence_sha256": SOURCE_SHA,
        "backend_id": "evidence-production-a",
        "deployment_scope": "PRODUCTION",
        "backend_state": "active",
        "encryption_at_rest": True,
        "immutability_mode": "WORM_COMPLIANCE",
        "retention_enforced": True,
        "legal_hold_supported": True,
        "privileged_delete_bypass": False,
        "public_access_blocked": True,
        "overwrite_protected": True,
        "integrity_digest": "sha256",
    }


class StaticEvidenceVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str]] = []

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        self.calls.append((evidence_ref, sha256))
        return self.accepted and evidence_ref == SOURCE_REF and sha256 == SOURCE_SHA


def test_committed_example_is_inert_and_cannot_pass() -> None:
    attestation = backend.load_attestation(ATTESTATION_PATH)
    result = backend.verify_backend_attestation(
        attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.backend_attestation_checks_passed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert "production evidence backend observation has not run" in result.findings


def test_fresh_custodied_production_observation_satisfies_contract() -> None:
    verifier = StaticEvidenceVerifier()
    result = backend.verify_backend_attestation(
        _observed_attestation(), evidence_verifier=verifier
    )
    assert result.backend_attestation_checks_passed is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert result.immutability_mode == "WORM_COMPLIANCE"
    assert result.source_evidence_verified is True
    assert verifier.calls == [(SOURCE_REF, SOURCE_SHA)]
    assert "LIVE_AUDIT_PERSISTENCE_NOT_RUN" in result.remaining_evidence


def test_default_evidence_verifier_refuses_observed_envelope() -> None:
    result = backend.verify_backend_attestation(_observed_attestation())
    assert result.backend_attestation_checks_passed is False
    assert result.source_evidence_verified is False
    assert "source backend observation evidence is not verified" in result.findings


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("deployment_scope", "PRE_PRODUCTION", "not scoped to production"),
        ("backend_state", "disabled", "not active"),
        ("encryption_at_rest", False, "encryption at rest"),
        ("immutability_mode", "WORM_GOVERNANCE", "WORM compliance"),
        ("retention_enforced", False, "retention enforcement"),
        ("legal_hold_supported", False, "legal hold"),
        ("privileged_delete_bypass", True, "delete bypass"),
        ("public_access_blocked", False, "public access"),
        ("overwrite_protected", False, "overwrite protection"),
    ],
)
def test_required_backend_control_mismatch_fails_closed(
    field: str, value: Any, needle: str
) -> None:
    attestation = _observed_attestation()
    attestation[field] = value
    result = backend.verify_backend_attestation(
        attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.backend_attestation_checks_passed is False
    assert any(needle in finding for finding in result.findings)


def test_stale_and_future_observations_fail_closed() -> None:
    stale = _observed_attestation()
    stale["observed_at"] = _iso(datetime.now(timezone.utc) - timedelta(minutes=16))
    stale_result = backend.verify_backend_attestation(
        stale, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("stale" in finding for finding in stale_result.findings)

    future = _observed_attestation()
    future["observed_at"] = _iso(datetime.now(timezone.utc) + timedelta(minutes=1))
    future_result = backend.verify_backend_attestation(
        future, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("future" in finding for finding in future_result.findings)


def test_unverified_source_evidence_fails_closed() -> None:
    result = backend.verify_backend_attestation(
        _observed_attestation(), evidence_verifier=StaticEvidenceVerifier(False)
    )
    assert result.backend_attestation_checks_passed is False
    assert result.source_evidence_verified is False


def test_secret_bearing_envelope_is_refused() -> None:
    attestation = _observed_attestation()
    attestation["client_secret"] = "forbidden"
    with pytest.raises(backend.EvidenceBackendAttestationError) as exc:
        backend.verify_backend_attestation(
            attestation, evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code in {
        "ATTESTATION_INVALID",
        "ATTESTATION_SECRET_MATERIAL_REFUSED",
    }


def test_example_yaml_remains_explicitly_not_run() -> None:
    document = yaml.safe_load(ATTESTATION_PATH.read_text(encoding="utf-8"))
    assert document["observation_status"] == "NOT_RUN"
    assert document["source_evidence_ref"] is None
    assert document["source_evidence_sha256"] is None


def test_source_has_no_provider_client_network_or_provisioning_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "boto3",
        "azure.storage",
        "google.cloud",
        "requests",
        "http.client",
        "socket",
        "subprocess",
        "terraform",
        "pulumi",
    ):
        assert forbidden not in source
    assert "DenyAllEvidenceVerifier" in source
    assert "promotion_allowed=False" in source
    assert "runtime_status=\"NOT_RUN\"" in source
