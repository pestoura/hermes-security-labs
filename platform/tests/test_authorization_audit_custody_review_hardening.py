from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_AUTH = ROOT / "platform" / "runner-authorization"
EVIDENCE = ROOT / "platform" / "evidence-plane"
ADAPTER_PATH = RUNNER_AUTH / "authorization_audit_adapter.py"
CUSTODY_PATH = EVIDENCE / "authorization_audit_custody.py"
POLICY_PATH = EVIDENCE / "authorization-audit-custody-policy.yaml"
STORE_PATH = EVIDENCE / "local_store.py"


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
    return _load(ADAPTER_PATH, "chg_hsl_079_review_authorization_audit_adapter")


def _custody() -> Any:
    return _load(CUSTODY_PATH, "chg_hsl_079_review_authorization_audit_custody")


def _store_module() -> Any:
    return _load(STORE_PATH, "chg_hsl_079_review_local_store")


def _event() -> dict[str, object]:
    return _adapter().build_authorization_audit_record(
        event_type="REGISTERED",
        phase="REGISTRATION",
        decision="ACCEPT",
        reason_code="RECEIPT_REGISTERED",
        authorization_ref="tb1-authz:v1:" + "a" * 64,
        duplicate=False,
        capability_id="web.discovery.headers",
        intrusiveness_level="L1",
    )


def _context() -> Any:
    adapter = _adapter()
    return adapter.AuthorizationAuditContext(
        campaign_id="campaign-079",
        run_id="run-079",
        step_id="step-079",
        attempt_id="attempt-079",
        principal="hermes-authorization",
        correlation_id="corr-079",
    )


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-079",
        "run_id": "run-079",
        "step_id": "step-079",
        "attempt_id": "attempt-079",
    }


def _event_kwargs() -> dict[str, object]:
    return {
        "event_type": "REGISTERED",
        "phase": "REGISTRATION",
        "decision": "ACCEPT",
        "reason_code": "RECEIPT_REGISTERED",
        "authorization_ref": "tb1-authz:v1:" + "a" * 64,
        "duplicate": False,
        "capability_id": "web.discovery.headers",
        "intrusiveness_level": "L1",
    }


def _enabled_policy() -> dict[str, Any]:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return policy


def _enabled_custody() -> Any:
    return _custody().AuthorizationAuditCustody(_enabled_policy())


@pytest.mark.parametrize(
    "forbidden",
    [
        "receipt",
        "receipt_json",
        "signature_b64",
        "authorization_ref",
        "target",
        "parameters",
        "credential",
        "secret",
        "token",
        "cookie",
        "headers",
    ],
)
def test_closed_schema_refuses_sensitive_extra_fields_before_write(
    tmp_path: Path, forbidden: str
) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = deepcopy(_event())
    event[forbidden] = "forbidden-sensitive-value"

    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(_enabled_policy()).persist(
            event,
            correlation=_correlation(),
            recorded_at="2026-08-16T05:20:00Z",
            evidence_store=store,
        )

    assert exc.value.code == "AUTHORIZATION_AUDIT_EVENT_INVALID"
    assert list(store.records.glob("ev_*.json")) == []
    assert list(store.objects.rglob("*")) == []


def test_policy_unknown_and_missing_fields_are_rejected() -> None:
    custody = _custody()

    unknown = _enabled_policy()
    unknown["unexpected"] = True
    findings = custody.validate_policy(unknown)
    assert findings
    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(unknown)
    assert exc.value.code == "POLICY_INVALID"

    missing = _enabled_policy()
    del missing["custody"]["include_raw_receipt"]
    findings = custody.validate_policy(missing)
    assert findings
    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(missing)
    assert exc.value.code == "POLICY_INVALID"


@pytest.mark.parametrize(
    ("recorded_at", "code"),
    [
        ("not-a-timestamp", "AUTHORIZATION_AUDIT_TIMESTAMP_INVALID"),
        ("2026-08-16T05:20:00+01:00", "AUTHORIZATION_AUDIT_TIMESTAMP_INVALID"),
    ],
)
def test_invalid_timestamp_fails_before_store_write(recorded_at: str, code: str) -> None:
    custody = _custody()

    class SpyStore:
        def __init__(self) -> None:
            self.put_calls = 0

        def put(self, record: object, payload: bytes) -> str:
            self.put_calls += 1
            return "ev_" + "1" * 32

        def verify(self, evidence_id: str) -> bool:
            return True

    store = SpyStore()
    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(_enabled_policy()).persist(
            _event(),
            correlation=_correlation(),
            recorded_at=recorded_at,
            evidence_store=store,
        )
    assert exc.value.code == code
    assert store.put_calls == 0


def test_invalid_correlation_identifier_fails_before_store_write() -> None:
    custody = _custody()

    class SpyStore:
        def __init__(self) -> None:
            self.put_calls = 0

        def put(self, record: object, payload: bytes) -> str:
            self.put_calls += 1
            return "ev_" + "1" * 32

        def verify(self, evidence_id: str) -> bool:
            return True

    store = SpyStore()
    correlation = _correlation()
    correlation["campaign_id"] = "invalid id with spaces"

    with pytest.raises(custody.AuthorizationAuditCustodyError) as exc:
        custody.AuthorizationAuditCustody(_enabled_policy()).persist(
            _event(),
            correlation=correlation,
            recorded_at="2026-08-16T05:20:00Z",
            evidence_store=store,
        )

    assert exc.value.code == "AUTHORIZATION_AUDIT_CORRELATION_INVALID"
    assert store.put_calls == 0


def test_chain_resolver_fails_closed_when_verifier_throws() -> None:
    custody = _custody()

    class ExplodingVerifier:
        def verify(self, evidence_ref: str, sha256: str) -> bool:
            raise RuntimeError("/secret/verifier/path/token")

    resolver = custody.EvidenceVerifierChainResolver(ExplodingVerifier())
    digest = "a" * 64
    assert resolver(
        object_ref=f"evidence://authorization-receipt-audit/{digest}",
        object_digest_sha256=digest,
        object_size_bytes=42,
    ) is False


@pytest.mark.parametrize(
    "bad_ref",
    [
        "evidence://EV_" + "1" * 32,
        "evidence://ev_" + "G" * 32,
        "evidence://ev_" + "1" * 31,
        "evidence://ev_" + "1" * 32 + "/",
        "ev_" + "A" * 32,
    ],
)
def test_noncanonical_custody_reference_fails_before_audit_append(bad_ref: str) -> None:
    adapter = _adapter()

    class FakeCustody:
        def persist(self, record: dict[str, object], **_kwargs: object) -> object:
            digest, size = adapter.authorization_audit_record_digest(record)
            return SimpleNamespace(
                evidence_id="ev_" + "1" * 32,
                evidence_ref=bad_ref,
                payload_sha256=digest,
                payload_size_bytes=size,
                classification="restricted",
            )

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "4" * 32,
        custody=FakeCustody(),
        evidence_store=object(),
        recorded_at_provider=lambda: "2026-08-16T05:20:00Z",
    )
    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())
    assert exc.value.code == "AUTHORIZATION_AUDIT_EVIDENCE_REF_INVALID"
    assert instance.length == 0


def test_evidence_id_and_evidence_ref_mismatch_fails_before_audit_append() -> None:
    adapter = _adapter()

    class FakeCustody:
        def persist(self, record: dict[str, object], **_kwargs: object) -> object:
            digest, size = adapter.authorization_audit_record_digest(record)
            return SimpleNamespace(
                evidence_id="ev_" + "1" * 32,
                evidence_ref="evidence://ev_" + "2" * 32,
                payload_sha256=digest,
                payload_size_bytes=size,
                classification="restricted",
            )

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "3" * 32,
        custody=FakeCustody(),
        evidence_store=object(),
        recorded_at_provider=lambda: "2026-08-16T05:20:00Z",
    )
    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())
    assert exc.value.code == "AUTHORIZATION_AUDIT_CUSTODY_MISMATCH"
    assert instance.length == 0


def test_custody_failure_never_leaks_backend_detail() -> None:
    adapter = _adapter()

    class FailingCustody:
        def persist(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("/secret/path/token")

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "2" * 32,
        custody=FailingCustody(),
        evidence_store=object(),
        recorded_at_provider=lambda: "2026-08-16T05:20:00Z",
    )
    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())
    assert exc.value.code == "AUTHORIZATION_AUDIT_CUSTODY_FAILED"
    assert "/secret/path/token" not in str(exc.value)
    assert instance.length == 0


def test_timestamp_provider_failure_is_sanitized_and_no_append_occurs() -> None:
    adapter = _adapter()

    def explode() -> str:
        raise RuntimeError("/secret/timestamp/provider")

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "1" * 32,
        custody=object(),
        evidence_store=object(),
        recorded_at_provider=explode,
    )
    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())
    assert exc.value.code == "AUTHORIZATION_AUDIT_CUSTODY_FAILED"
    assert "/secret/timestamp/provider" not in str(exc.value)
    assert instance.length == 0


def test_persisted_metadata_cannot_claim_runtime_or_execution_authority(tmp_path: Path) -> None:
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    result = _enabled_custody().persist(
        _event(),
        correlation=_correlation(),
        recorded_at="2026-08-16T05:20:00Z",
        evidence_store=store,
    )
    record = store.get_record(result.evidence_id)
    metadata = record["metadata"]

    assert metadata["promotion_allowed"] is False
    assert metadata["runtime_status"] == "NOT_RUN"
    assert metadata["execution_authority"] == "NONE"


def test_retry_after_audit_append_failure_reuses_one_custody_object_and_one_final_entry(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "0" * 32,
        custody=_enabled_custody(),
        evidence_store=store,
        recorded_at_provider=lambda: "2026-08-16T05:20:00Z",
    )
    real_sink = instance._sink

    class FailOnceSink:
        def __init__(self) -> None:
            self.failed = False

        def append(self, **kwargs: object) -> object:
            if not self.failed:
                self.failed = True
                raise adapter.AuditSinkError("synthetic append failure")
            return real_sink.append(**kwargs)

        @property
        def length(self) -> int:
            return real_sink.length

        def seal(self, *, sealed_at: str | None = None) -> dict[str, Any]:
            return real_sink.seal(sealed_at=sealed_at)

        def verify(self, *, resolver: Any | None = None) -> dict[str, Any]:
            return real_sink.verify(resolver=resolver)

    instance._sink = FailOnceSink()

    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())
    assert exc.value.code == "AUTHORIZATION_AUDIT_APPEND_FAILED"
    assert instance.length == 0
    assert len(list(store.records.glob("ev_*.json"))) == 1

    first_record_id = next(store.records.glob("ev_*.json")).stem
    returned = instance.record_event(context=_context(), **_event_kwargs())
    assert returned["schema_version"] == "authorization-receipt-audit/v1"
    assert instance.length == 1
    assert len(list(store.records.glob("ev_*.json"))) == 1
    assert next(store.records.glob("ev_*.json")).stem == first_record_id
    assert instance.seal()["entries"][0]["evidence_ref"] == first_record_id
