from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_AUTH = ROOT / "platform" / "runner-authorization"
EVIDENCE = ROOT / "platform" / "evidence-plane"
CUSTODY_PATH = EVIDENCE / "authorization_audit_custody.py"
POLICY_PATH = EVIDENCE / "authorization-audit-custody-policy.yaml"
ADAPTER_PATH = RUNNER_AUTH / "authorization_audit_adapter.py"
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


def _adapter() -> Any:
    return _load(ADAPTER_PATH, "chg_hsl_079_authorization_audit_adapter")


def _custody() -> Any:
    return _load(CUSTODY_PATH, "chg_hsl_079_authorization_audit_custody")


def _store_module() -> Any:
    return _load(STORE_PATH, "chg_hsl_079_local_store")


def _verifier_module() -> Any:
    return _load(VERIFIER_PATH, "chg_hsl_079_local_verifier")


def _event(event_type: str = "REGISTERED") -> dict[str, object]:
    adapter = _adapter()
    matrix = {
        "REGISTERED": ("REGISTRATION", "ACCEPT", "RECEIPT_REGISTERED"),
        "LOOKUP_HIT": ("LOOKUP", "ACCEPT", "AUTHORIZATION_FOUND"),
        "LOOKUP_MISS": ("LOOKUP", "DENY", "AUTHORIZATION_NOT_FOUND"),
        "LOOKUP_EXPIRED": ("LOOKUP", "DENY", "AUTHORIZATION_EXPIRED"),
        "REFUSED": ("DELIVERY", "DENY", "DELIVERY_REFUSED"),
    }
    phase, decision, reason = matrix[event_type]
    return adapter.build_authorization_audit_record(
        event_type=event_type,
        phase=phase,
        decision=decision,
        reason_code=reason,
        authorization_ref="tb1-authz:v1:" + "a" * 64,
        duplicate=False,
        capability_id="web.discovery.headers" if decision == "ACCEPT" else None,
        intrusiveness_level="L1" if decision == "ACCEPT" else None,
    )


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-079",
        "run_id": "run-079",
        "step_id": "step-079",
        "attempt_id": "attempt-079",
    }


def _enabled_policy() -> dict[str, Any]:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return policy


def test_canonical_policy_is_disabled_and_fail_closed() -> None:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["custody"]["classification"] == "restricted"
    assert policy["custody"]["include_raw_receipt"] is False
    assert policy["custody"]["include_raw_authorization_ref"] is False
    assert custody.validate_policy(policy) == []

    bridge = custody.AuthorizationAuditCustody(policy)
    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T04:50:00Z",
            evidence_store=object(),
        )
    assert exc.value.code == "CUSTODY_DISABLED"


@pytest.mark.parametrize(
    "event_type",
    ["REGISTERED", "LOOKUP_HIT", "LOOKUP_MISS", "LOOKUP_EXPIRED", "REFUSED"],
)
def test_enabled_test_policy_projects_exact_sanitized_record(
    tmp_path: Path, event_type: str
) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = _event(event_type)
    result = custody.AuthorizationAuditCustody(_enabled_policy()).persist(
        event,
        correlation=_correlation(),
        recorded_at="2026-08-16T04:50:00Z",
        evidence_store=store,
    )

    digest, size = _adapter().authorization_audit_record_digest(event)
    assert result.payload_sha256 == digest
    assert result.payload_size_bytes == size
    assert result.evidence_ref == f"evidence://{result.evidence_id}"
    assert result.classification == "restricted"
    assert store.verify(result.evidence_id) is True

    record = store.get_record(result.evidence_id)
    assert record["classification"] == "restricted"
    assert record["correlation"] == _correlation()
    assert record["origin"]["producer"] == "authorization-receipt-audit-custody-v1"
    assert record["origin"]["operation"] == f"authorization.audit.{event_type}"
    assert record["content"]["sha256"] == digest
    assert record["content"]["size_bytes"] == size
    assert record["content"]["storage_ref"] == (
        f"evidence://authorization-receipt-audit/{digest}"
    )
    assert record["retention"]["policy_id"] == "default-30d"

    object_path = store.objects / digest[:2] / digest
    decoded = json.loads(object_path.read_text(encoding="utf-8"))
    assert decoded == event
    serialized = object_path.read_text(encoding="utf-8")
    assert "tb1-authz:v1:" not in serialized
    for forbidden_field in (
        "receipt_json",
        "signature_b64",
        "private_key",
        "credential",
        "secret",
        "token",
        "cookie",
        "headers",
    ):
        assert forbidden_field not in decoded


def test_identical_persistence_is_idempotent_in_canonical_store(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    bridge = custody.AuthorizationAuditCustody(_enabled_policy())
    kwargs = {
        "correlation": _correlation(),
        "recorded_at": "2026-08-16T04:50:00Z",
        "evidence_store": store,
    }
    first = bridge.persist(_event(), **kwargs)
    second = bridge.persist(_event(), **kwargs)
    assert second.evidence_id == first.evidence_id
    assert second.payload_sha256 == first.payload_sha256
    assert second.payload_size_bytes == first.payload_size_bytes
    assert len(list(store.records.glob("ev_*.json"))) == 1


def test_local_evidence_verifier_binds_exact_ref_digest_and_storage_ref(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    result = custody.AuthorizationAuditCustody(_enabled_policy()).persist(
        _event(),
        correlation=_correlation(),
        recorded_at="2026-08-16T04:50:00Z",
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

    digest = record["content"]["sha256"]
    object_path = store.objects / digest[:2] / digest
    object_path.write_bytes(b"tampered")
    assert verifier.verify(result.evidence_ref, result.payload_sha256) is False
    assert verifier.verify(storage_ref, result.payload_sha256) is False


def test_chain_resolver_is_only_interface_adapter_and_fails_closed() -> None:
    custody = _custody()

    class Verifier:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def verify(self, evidence_ref: str, sha256: str) -> bool:
            self.calls.append((evidence_ref, sha256))
            return True

    verifier = Verifier()
    resolver = custody.EvidenceVerifierChainResolver(verifier)
    digest = "a" * 64
    ref = "evidence://authorization-receipt-audit/" + digest
    assert resolver(
        object_ref=ref,
        object_digest_sha256=digest,
        object_size_bytes=42,
    ) is True
    assert verifier.calls == [(ref, digest)]
    assert resolver(object_ref="", object_digest_sha256=digest, object_size_bytes=42) is False
    assert resolver(object_ref=ref, object_digest_sha256=digest, object_size_bytes=True) is False


def test_invalid_or_sensitive_extra_field_is_refused_before_write(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = deepcopy(_event())
    event["token"] = "forbidden"
    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(_enabled_policy()).persist(
            event,
            correlation=_correlation(),
            recorded_at="2026-08-16T04:50:00Z",
            evidence_store=store,
        )
    assert exc.value.code == "AUTHORIZATION_AUDIT_EVENT_INVALID"
    assert list(store.records.glob("*.json")) == []


def test_store_contract_and_backend_failures_fail_closed_without_leakage() -> None:
    custody = _custody()
    bridge = custody.AuthorizationAuditCustody(_enabled_policy())

    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T04:50:00Z",
            evidence_store=None,
        )
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"

    class FailingStore:
        def put(self, record: object, payload: bytes) -> str:
            raise RuntimeError("/sensitive/backend/path/token")

        def verify(self, evidence_id: str) -> bool:
            return True

    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T04:50:00Z",
            evidence_store=FailingStore(),
        )
    assert exc.value.code == "EVIDENCE_PROJECTION_FAILED"
    assert "/sensitive/backend/path/token" not in str(exc.value)


@pytest.mark.parametrize("mode", ["false", "raise"])
def test_post_write_verification_failure_fails_closed(mode: str) -> None:
    custody = _custody()
    bridge = custody.AuthorizationAuditCustody(_enabled_policy())

    class UnverifiedStore:
        def put(self, record: object, payload: bytes) -> str:
            return "ev_" + "1" * 32

        def verify(self, evidence_id: str) -> bool:
            if mode == "raise":
                raise RuntimeError("/sensitive/verify/path")
            return False

    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T04:50:00Z",
            evidence_store=UnverifiedStore(),
        )
    assert exc.value.code == "EVIDENCE_VERIFICATION_FAILED"
    assert "/sensitive/verify/path" not in str(exc.value)
