from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESOLVER_PATH = ROOT / "platform" / "runner-authorization" / "verified_authorization_resolver.py"
DELIVERY_PATH = ROOT / "platform" / "runner-authorization" / "receipt_delivery.py"
AUDIT_PATH = ROOT / "platform" / "runner-authorization" / "authorization_audit_adapter.py"
WEBGOAT_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"

AUTH_REF = "tb1-authz:v1:" + "1" * 64
OTHER_REF = "tb1-authz:v1:" + "2" * 64
CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"
PEER = {"uid": 4242, "principal": "hexor.control-plane"}


def _load(path: Path, name: str) -> Any:
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


def _resolver_module():
    return _load(RESOLVER_PATH, "chg_hsl_078_resolver")


def _delivery_module():
    return _load(DELIVERY_PATH, "chg_hsl_078_delivery")


def _audit_module():
    return _load(AUDIT_PATH, "chg_hsl_078_audit")


def _webgoat_module():
    return _load(WEBGOAT_PATH, "chg_hsl_078_webgoat")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _context() -> dict[str, str]:
    return {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "principal": "hexor.runner.webgoat-l1",
        "correlation_id": "fixture-webgoat-key-one",
    }


@dataclass(frozen=True)
class VerifiedStub:
    authorization_ref: str
    issued_at: str
    expires_at: str
    campaign_id: str = CAMPAIGN_ID
    run_id: str = RUN_ID
    step_id: str = STEP_ID
    operation_id: str = "web.discovery.headers"
    operation_version: str = "1.0.0"
    operation_parameters_sha256: str = "0" * 64
    capability_id: str = "web.discovery.headers"
    target_sha256: str = "0" * 64
    intrusiveness_level: str = "L1"


def _verified(*, ref: str = AUTH_REF, expired: bool = False) -> VerifiedStub:
    now = datetime.now(timezone.utc)
    if expired:
        issued = now - timedelta(minutes=2)
        expires = now - timedelta(seconds=1)
    else:
        issued = now - timedelta(seconds=30)
        expires = now + timedelta(minutes=5)
    return VerifiedStub(
        authorization_ref=ref,
        issued_at=_iso(issued),
        expires_at=_iso(expires),
    )


def _resolver_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.resolver",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "verification_source": "platform/authorization-contract/authorization_receipt.py",
        "trust_store_path": "/tmp/chg-hsl-078-trust.json",
        "cache": {"mode": "memory-only", "max_entries": 16, "persistence": "none"},
    }


def _delivery_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.receipt-delivery",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "issuer": "hermes-control-plane",
        "channel": {
            "kind": "local-authenticated",
            "transport": "af_unix-peercred",
            "socket_path": "/run/hexor/runner-authz.sock",
            "allowed_peer_principal": PEER["principal"],
            "allowed_peer_uid": PEER["uid"],
            "require_monotonic_sequence": True,
        },
        "runner_private_key": "forbidden",
        "persistence": "none",
        "restart_behaviour": "fail-closed-empty",
    }


class RecordingObserver:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[dict[str, Any]] = []

    def record_event(self, **event: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("backend detail must not escape")
        self.events.append(dict(event))
        return dict(event)


# ---------------------------------------------------------------- resolver audit


def test_resolver_audits_hit_miss_and_expiry_with_trusted_context(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _resolver_module()
    observer = RecordingObserver()
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=observer)
    live = _verified()
    monkeypatch.setattr(
        module.authorization_contract,
        "verify_authorization_receipt",
        lambda receipt, trust_store: live,
    )
    resolver.register_receipt({"fixture": "signed-receipt-not-retained"})

    assert resolver.resolve(AUTH_REF, audit_context=_context()) == live
    assert observer.events[-1]["event_type"] == "LOOKUP_HIT"
    assert observer.events[-1]["reason_code"] == "AUTHORIZATION_LIVE"
    assert observer.events[-1]["context"] == _context()
    assert observer.events[-1]["capability_id"] == "web.discovery.headers"

    assert resolver.resolve(OTHER_REF, audit_context=_context()) is None
    assert observer.events[-1]["event_type"] == "LOOKUP_MISS"
    assert observer.events[-1]["reason_code"] == "AUTHORIZATION_NOT_FOUND"

    expired = replace(live, issued_at=_verified(expired=True).issued_at, expires_at=_verified(expired=True).expires_at)
    resolver._entries[AUTH_REF] = expired  # explicit repository-only expiry fixture
    assert resolver.resolve(AUTH_REF, audit_context=_context()) is None
    assert observer.events[-1]["event_type"] == "LOOKUP_EXPIRED"
    assert observer.events[-1]["reason_code"] == "AUTHORIZATION_NOT_LIVE"
    assert resolver.size == 0


def test_resolver_invalid_reference_audits_null_safe_reference_and_denies() -> None:
    module = _resolver_module()
    real_audit = _audit_module().CanonicalAuthorizationAuditAdapter(chain_id="chain_" + "a" * 32)
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=real_audit)
    assert resolver.resolve("raw invalid reference with spaces", audit_context=_context()) is None
    document = real_audit.seal(sealed_at="2026-08-16T03:50:00Z")
    assert document["entries"][0]["audit"]["decision"] == "LOOKUP_MISS"
    assert "raw invalid reference" not in str(document)


def test_resolver_with_observer_and_missing_context_never_returns_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _resolver_module()
    observer = RecordingObserver()
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=observer)
    live = _verified()
    monkeypatch.setattr(module.authorization_contract, "verify_authorization_receipt", lambda receipt, trust_store: live)
    resolver.register_receipt({})
    assert resolver.resolve(AUTH_REF) is None
    assert observer.events == []


def test_resolver_audit_failure_on_lookup_hit_returns_no_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _resolver_module()
    observer = RecordingObserver(fail=True)
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=observer)
    live = _verified()
    monkeypatch.setattr(module.authorization_contract, "verify_authorization_receipt", lambda receipt, trust_store: live)
    resolver.register_receipt({})
    assert resolver.resolve(AUTH_REF, audit_context=_context()) is None


# ---------------------------------------------------------------- delivery audit


class DeliveryResolver:
    def __init__(self, *, verified: VerifiedStub | None = None, error: Exception | None = None) -> None:
        self.verified = verified or _verified()
        self.error = error
        self.register_calls = 0
        self.forgotten: list[str] = []

    def register_receipt(self, receipt: dict[str, Any]) -> VerifiedStub:
        self.register_calls += 1
        if self.error is not None:
            raise self.error
        return self.verified

    def forget(self, authorization_ref: str) -> bool:
        self.forgotten.append(authorization_ref)
        return True


def _envelope(*, sequence: int = 1) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "issuer": "hermes-control-plane",
        "sequence": sequence,
        "receipt": {"fixture": "opaque-signed-receipt"},
    }


def test_delivery_success_audits_once_and_exact_duplicate_creates_no_second_registration() -> None:
    module = _delivery_module()
    resolver = DeliveryResolver()
    observer = RecordingObserver()
    delivery = module.TrustedReceiptDelivery(_delivery_policy(), resolver, audit_observer=observer)

    first = delivery.deliver(_envelope(sequence=7), peer=PEER, audit_context=_context())
    second = delivery.deliver(_envelope(sequence=7), peer=PEER, audit_context=_context())

    assert first.accepted is True and first.duplicate is False
    assert second.accepted is True and second.duplicate is True
    assert resolver.register_calls == 1
    assert len(observer.events) == 1
    event = observer.events[0]
    assert event["event_type"] == "REGISTERED"
    assert event["phase"] == "REGISTRATION"
    assert event["decision"] == "ACCEPT"
    assert event["reason_code"] == "RECEIPT_VERIFIED"
    assert event["authorization_ref"] == AUTH_REF
    assert event["capability_id"] == "web.discovery.headers"
    assert event["intrusiveness_level"] == "L1"


def test_delivery_audit_failure_after_registration_rolls_back_local_resolvability() -> None:
    module = _delivery_module()
    resolver = DeliveryResolver()
    delivery = module.TrustedReceiptDelivery(
        _delivery_policy(), resolver, audit_observer=RecordingObserver(fail=True)
    )
    with pytest.raises(module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(), peer=PEER, audit_context=_context())
    assert exc.value.code == "DELIVERY_AUDIT_FAILED"
    assert resolver.forgotten == [AUTH_REF]
    assert delivery.last_sequence is None


def test_delivery_refusal_is_audited_with_stable_code_and_never_registers() -> None:
    module = _delivery_module()
    resolver = DeliveryResolver()
    observer = RecordingObserver()
    delivery = module.TrustedReceiptDelivery(_delivery_policy(), resolver, audit_observer=observer)
    bad_peer = {"uid": 1, "principal": PEER["principal"]}
    with pytest.raises(module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(), peer=bad_peer, audit_context=_context())
    assert exc.value.code == "PEER_UID_UNAUTHORIZED"
    assert resolver.register_calls == 0
    assert observer.events[-1]["event_type"] == "REFUSED"
    assert observer.events[-1]["phase"] == "DELIVERY"
    assert observer.events[-1]["reason_code"] == "PEER_UID_UNAUTHORIZED"
    assert observer.events[-1]["authorization_ref"] is None


def test_delivery_verification_refusal_uses_stable_resolver_code_only() -> None:
    module = _delivery_module()
    resolver_error = module.resolver_module.AuthorizationResolverError(
        "TB1_AUTH_SIGNATURE_INVALID", "private backend detail"
    )
    resolver = DeliveryResolver(error=resolver_error)
    observer = RecordingObserver()
    delivery = module.TrustedReceiptDelivery(_delivery_policy(), resolver, audit_observer=observer)
    with pytest.raises(module.resolver_module.AuthorizationResolverError):
        delivery.deliver(_envelope(), peer=PEER, audit_context=_context())
    event = observer.events[-1]
    assert event["event_type"] == "REFUSED"
    assert event["phase"] == "REGISTRATION"
    assert event["reason_code"] == "TB1_AUTH_SIGNATURE_INVALID"
    assert "private backend detail" not in str(event)


def test_refusal_audit_failure_cannot_convert_denial_to_success() -> None:
    module = _delivery_module()
    resolver = DeliveryResolver()
    delivery = module.TrustedReceiptDelivery(
        _delivery_policy(), resolver, audit_observer=RecordingObserver(fail=True)
    )
    with pytest.raises(module.ReceiptDeliveryError) as exc:
        delivery.deliver(
            _envelope(),
            peer={"uid": 1, "principal": PEER["principal"]},
            audit_context=_context(),
        )
    assert exc.value.code == "DELIVERY_AUDIT_FAILED"
    assert resolver.register_calls == 0


# ---------------------------------------------------------------- adapter idempotency


def test_exact_duplicate_audit_observation_is_idempotent_above_canonical_sink() -> None:
    module = _audit_module()
    adapter = module.CanonicalAuthorizationAuditAdapter(chain_id="chain_" + "b" * 32)
    context = module.AuthorizationAuditContext(**_context())
    kwargs = {
        "context": context,
        "event_type": "LOOKUP_HIT",
        "phase": "LOOKUP",
        "decision": "ACCEPT",
        "reason_code": "AUTHORIZATION_LIVE",
        "authorization_ref": AUTH_REF,
        "duplicate": False,
        "capability_id": "web.discovery.headers",
        "intrusiveness_level": "L1",
    }
    first = adapter.record_event(**kwargs)
    second = adapter.record_event(**kwargs)
    assert second == first
    assert adapter.length == 1


# ---------------------------------------------------------------- WebGoat request-bound context


class ContextCapturingResolver:
    def __init__(self, binding: Any) -> None:
        self.binding = binding
        self.contexts: list[dict[str, str]] = []

    def resolve(self, authorization_ref: str, *, audit_context: dict[str, str]) -> Any:
        assert authorization_ref == AUTH_REF
        self.contexts.append(dict(audit_context))
        return self.binding


class Probe:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *, timeout_seconds: float) -> Any:
        del timeout_seconds
        self.calls += 1
        return _webgoat_module().ProbeResponse(status=200, headers=(("Server", "WebGoat"),))


def _webgoat_request() -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
        },
        "emitted_at": "2026-08-16T03:40:00Z",
        "authorization_ref": AUTH_REF,
        "idempotency_key": "fixture-webgoat-key-one",
        "operation": {
            "capability_id": "web.discovery.headers",
            "input": {
                "operation_id": "web.discovery.headers",
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "webgoat-web"},
                "parameters": {"follow_redirects": False},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 0},
    }


def test_webgoat_passes_schema_validated_request_context_to_audited_resolver(tmp_path: Path) -> None:
    module = _webgoat_module()
    request = _webgoat_request()
    payload = request["operation"]["input"]
    now = datetime.now(timezone.utc)
    binding = VerifiedStub(
        authorization_ref=AUTH_REF,
        issued_at=_iso(now - timedelta(seconds=30)),
        expires_at=_iso(now + timedelta(minutes=5)),
        operation_parameters_sha256=module.authorization_contract.canonical_parameters_sha256(
            payload["parameters"]
        ),
        target_sha256=module.gateway_contract.canonical_target_digest(payload["target"]),
    )
    resolver = ContextCapturingResolver(binding)
    probe = Probe()
    runner = module.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=resolver,
        probe=probe,
    )
    outcome = runner.dispatch(request)["messages"][0]
    assert outcome["status"] == "PASS"
    assert probe.calls == 1
    assert resolver.contexts == [
        {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "principal": "hexor.runner.webgoat-l1",
            "correlation_id": "fixture-webgoat-key-one",
        }
    ]
    serialized = str(resolver.contexts[0])
    assert "target" not in serialized
    assert "parameters" not in serialized
