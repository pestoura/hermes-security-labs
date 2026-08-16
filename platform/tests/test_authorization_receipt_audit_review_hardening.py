from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESOLVER_PATH = ROOT / "platform" / "runner-authorization" / "verified_authorization_resolver.py"
DELIVERY_PATH = ROOT / "platform" / "runner-authorization" / "receipt_delivery.py"

AUTH_REF = "tb1-authz:v1:" + "1" * 64
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
    return _load(RESOLVER_PATH, "chg_hsl_078_review_resolver")


def _delivery_module():
    return _load(DELIVERY_PATH, "chg_hsl_078_review_delivery")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _context() -> dict[str, str]:
    return {
        "campaign_id": "campaign-078",
        "run_id": "run-078",
        "step_id": "step-078",
        "attempt_id": "attempt-078",
        "principal": "hexor.runner.webgoat-l1",
        "correlation_id": "correlation-078",
    }


def _unsafe_context() -> dict[str, str]:
    value = _context()
    value["principal"] = "unsafe principal with spaces"
    return value


def _resolver_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.resolver",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "verification_source": "platform/authorization-contract/authorization_receipt.py",
        "trust_store_path": "/tmp/chg-hsl-078-review-trust.json",
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


@dataclass(frozen=True)
class VerifiedStub:
    authorization_ref: str = AUTH_REF
    issued_at: str = ""
    expires_at: str = ""
    capability_id: str = "web.discovery.headers"
    intrusiveness_level: str = "L1"


def _live_verified() -> VerifiedStub:
    now = datetime.now(timezone.utc)
    return VerifiedStub(
        issued_at=_iso(now - timedelta(seconds=30)),
        expires_at=_iso(now + timedelta(minutes=5)),
    )


class RecordingObserver:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[dict[str, Any]] = []

    def record_event(self, **event: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("private audit backend detail")
        self.events.append(dict(event))
        return dict(event)


class RollbackResolver:
    def __init__(self, *, rollback: str = "false") -> None:
        self.rollback = rollback

    def register_receipt(self, receipt: dict[str, Any]) -> VerifiedStub:
        del receipt
        return _live_verified()

    def forget(self, authorization_ref: str) -> bool:
        assert authorization_ref == AUTH_REF
        if self.rollback == "raise":
            raise RuntimeError("private rollback backend detail")
        return self.rollback == "true"


def _envelope() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "issuer": "hermes-control-plane",
        "sequence": 1,
        "receipt": {"fixture": "opaque-signed-receipt"},
    }


def test_prefixed_but_malformed_authorization_ref_is_classified_invalid() -> None:
    module = _resolver_module()
    observer = RecordingObserver()
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=observer)

    malformed = "tb1-authz:v1:not-a-64-char-lowercase-digest"
    assert resolver.resolve(malformed, audit_context=_context()) is None
    assert observer.events[-1]["event_type"] == "LOOKUP_MISS"
    assert observer.events[-1]["reason_code"] == "AUTHORIZATION_REF_INVALID"


def test_resolver_rejects_unsafe_trusted_context_even_with_permissive_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _resolver_module()
    observer = RecordingObserver()
    resolver = module.VerifiedAuthorizationResolver(_resolver_policy(), audit_observer=observer)
    live = _live_verified()
    monkeypatch.setattr(
        module.authorization_contract,
        "verify_authorization_receipt",
        lambda receipt, trust_store: live,
    )
    resolver.register_receipt({})

    assert resolver.resolve(AUTH_REF, audit_context=_unsafe_context()) is None
    assert observer.events == []


def test_delivery_rejects_unsafe_trusted_context_before_registration() -> None:
    module = _delivery_module()
    resolver = RollbackResolver(rollback="true")
    observer = RecordingObserver()
    delivery = module.TrustedReceiptDelivery(
        _delivery_policy(), resolver, audit_observer=observer
    )

    with pytest.raises(module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(), peer=PEER, audit_context=_unsafe_context())
    assert exc.value.code == "DELIVERY_AUDIT_CONTEXT_REQUIRED"
    assert observer.events == []


@pytest.mark.parametrize("rollback", ["false", "raise"])
def test_post_registration_audit_failure_surfaces_rollback_failure_without_leakage(
    rollback: str,
) -> None:
    module = _delivery_module()
    delivery = module.TrustedReceiptDelivery(
        _delivery_policy(),
        RollbackResolver(rollback=rollback),
        audit_observer=RecordingObserver(fail=True),
    )

    with pytest.raises(module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(), peer=PEER, audit_context=_context())
    assert exc.value.code == "DELIVERY_AUDIT_ROLLBACK_FAILED"
    assert "private" not in str(exc.value).lower()
    assert delivery.last_sequence is None
