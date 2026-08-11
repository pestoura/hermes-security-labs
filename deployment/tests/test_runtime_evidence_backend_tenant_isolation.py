from __future__ import annotations

import hashlib
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
    / "runtime_evidence_backend_tenant_isolation.py"
)
ATTESTATION_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "evidence-backend-tenant-isolation-attestation.example.yaml"
)
SOURCE_REF = "evidence://runner-live/backend/tenant-isolation/fixture.json"
SOURCE_SHA = hashlib.sha256(b"tenant-isolation-source-fixture").hexdigest()
SUBJECT_TENANT = hashlib.sha256(b"subject-tenant-fixture").hexdigest()
PEER_TENANT = hashlib.sha256(b"peer-tenant-fixture").hexdigest()


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


isolation = _load("runtime_evidence_backend_tenant_isolation_test", MODULE_PATH)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _observed_attestation() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "tenant-isolation-observation-fixture",
        "observation_source": "provider-read-only-metadata-and-negative-tests",
        "observed_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=10)),
        "source_evidence_ref": SOURCE_REF,
        "source_evidence_sha256": SOURCE_SHA,
        "backend_id": "evidence-production-a",
        "subject_tenant_sha256": SUBJECT_TENANT,
        "peer_tenant_sha256": PEER_TENANT,
        "namespace_isolated": True,
        "access_policy_isolated": True,
        "encryption_context_isolated": True,
        "shared_writable_namespace": False,
        "cross_tenant_list_result": "DENIED",
        "cross_tenant_read_result": "DENIED",
        "cross_tenant_write_result": "DENIED",
    }


class StaticEvidenceVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str]] = []

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        self.calls.append((evidence_ref, sha256))
        return self.accepted and evidence_ref == SOURCE_REF and sha256 == SOURCE_SHA


def test_committed_example_is_inert_and_cannot_pass() -> None:
    attestation = isolation.load_attestation(ATTESTATION_PATH)
    result = isolation.verify_tenant_isolation_attestation(
        attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.tenant_isolation_checks_passed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert "production tenant-isolation observation has not run" in result.findings


def test_fresh_custodied_negative_observation_satisfies_contract() -> None:
    verifier = StaticEvidenceVerifier()
    result = isolation.verify_tenant_isolation_attestation(
        _observed_attestation(), evidence_verifier=verifier
    )
    assert result.tenant_isolation_checks_passed is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert result.subject_tenant_sha256 != result.peer_tenant_sha256
    assert result.source_evidence_verified is True
    assert verifier.calls == [(SOURCE_REF, SOURCE_SHA)]


def test_default_evidence_verifier_refuses_observed_envelope() -> None:
    result = isolation.verify_tenant_isolation_attestation(_observed_attestation())
    assert result.tenant_isolation_checks_passed is False
    assert result.source_evidence_verified is False
    assert "source tenant-isolation evidence is not verified" in result.findings


def test_same_tenant_digest_cannot_be_used_as_negative_pair() -> None:
    attestation = _observed_attestation()
    attestation["peer_tenant_sha256"] = attestation["subject_tenant_sha256"]
    result = isolation.verify_tenant_isolation_attestation(
        attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.tenant_isolation_checks_passed is False
    assert any("distinct tenants" in finding for finding in result.findings)


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("namespace_isolated", False, "namespace isolation"),
        ("access_policy_isolated", False, "access-policy isolation"),
        ("encryption_context_isolated", False, "encryption context"),
        ("shared_writable_namespace", True, "share a writable"),
        ("cross_tenant_list_result", "ALLOWED", "list was not denied"),
        ("cross_tenant_read_result", "ALLOWED", "read was not denied"),
        ("cross_tenant_write_result", "ALLOWED", "write was not denied"),
        ("cross_tenant_read_result", "NOT_RUN", "read was not denied"),
    ],
)
def test_isolation_control_or_negative_mismatch_fails_closed(
    field: str, value: Any, needle: str
) -> None:
    attestation = _observed_attestation()
    attestation[field] = value
    result = isolation.verify_tenant_isolation_attestation(
        attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.tenant_isolation_checks_passed is False
    assert any(needle in finding for finding in result.findings)


def test_stale_and_future_observations_fail_closed() -> None:
    stale = _observed_attestation()
    stale["observed_at"] = _iso(datetime.now(timezone.utc) - timedelta(minutes=16))
    stale_result = isolation.verify_tenant_isolation_attestation(
        stale, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("stale" in finding for finding in stale_result.findings)

    future = _observed_attestation()
    future["observed_at"] = _iso(datetime.now(timezone.utc) + timedelta(minutes=1))
    future_result = isolation.verify_tenant_isolation_attestation(
        future, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("future" in finding for finding in future_result.findings)


def test_customer_or_secret_bearing_envelope_is_refused() -> None:
    for field in ("customer_name", "client_secret"):
        attestation = _observed_attestation()
        attestation[field] = "forbidden"
        with pytest.raises(isolation.TenantIsolationAttestationError) as exc:
            isolation.verify_tenant_isolation_attestation(
                attestation, evidence_verifier=StaticEvidenceVerifier()
            )
        assert exc.value.code in {
            "ATTESTATION_INVALID",
            "ATTESTATION_IDENTIFYING_OR_SECRET_MATERIAL_REFUSED",
        }


def test_example_contains_hashes_only_and_negative_tests_not_run() -> None:
    document = yaml.safe_load(ATTESTATION_PATH.read_text(encoding="utf-8"))
    assert document["observation_status"] == "NOT_RUN"
    assert len(document["subject_tenant_sha256"]) == 64
    assert len(document["peer_tenant_sha256"]) == 64
    assert document["cross_tenant_list_result"] == "NOT_RUN"
    assert document["cross_tenant_read_result"] == "NOT_RUN"
    assert document["cross_tenant_write_result"] == "NOT_RUN"
    assert "tenant_name" not in document
    assert "customer_name" not in document


def test_source_has_no_provider_client_network_or_mutation_path() -> None:
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
