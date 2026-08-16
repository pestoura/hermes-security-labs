#!/usr/bin/env python3
"""Trusted local composition boundary that delivers signed TB1 receipts to the Runner.

This module is the smallest operational answer to the open blocker recorded in
``platform/runner-authorization/README.md``: *how does a verified receipt reach the
Runner process?*

Design constraints enforced here:

* Hermes/TB1 is the sole issuer. The envelope issuer must equal the canonical
  contract issuer; nothing else can populate the resolver.
* The caller controls no receipt content and no trust/verification field. Any
  attempt to assert verification state, execution authority or trust level in the
  envelope or receipt fails closed before verification is attempted.
* The Runner never holds a private key. Any secret-shaped material fails closed.
* Delivery is authenticated locally by AF_UNIX peer credentials (uid + principal),
  never by a network claim and never by a field inside ``runner.step.request``.
* Restart semantics are fail-closed: the sequence baseline and the resolver cache
  are memory-only, so a restarted Runner resolves nothing until Hermes redelivers.
* An optional audit observer records sanitized registration/refusal decisions. When
  configured, a successful registration is not accepted until the audit append
  succeeds; failed post-registration audit is rolled back through resolver.forget().

The module performs no signature verification of its own: it delegates to the
canonical verifier through ``VerifiedAuthorizationResolver.register_receipt``.
It opens no socket, starts no process and issues no authorization.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / "receipt-delivery-policy.yaml"
RESOLVER_PATH = HERE / "verified_authorization_resolver.py"

ENVELOPE_FIELDS = {"schema_version", "issuer", "sequence", "receipt"}
PEER_FIELDS = {"uid", "principal"}
AUDIT_CONTEXT_FIELDS = {
    "campaign_id",
    "run_id",
    "step_id",
    "attempt_id",
    "principal",
    "correlation_id",
}

FORBIDDEN_TRUST_FIELDS = {
    "verified",
    "is_verified",
    "trusted",
    "trust_level",
    "trust_state",
    "execution_authority",
    "authorization_state",
    "authorization_decision",
    "verification_source",
    "bypass",
    "force",
}

FORBIDDEN_SECRET_FIELDS = {
    "private_key",
    "privatekey",
    "secret",
    "secret_key",
    "seed",
    "passphrase",
    "password",
    "token",
    "cookie",
    "credential",
    "api_key",
    "signing_key",
}


def _load_resolver_module() -> Any:
    name = "runner_authorization_resolver_for_delivery"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, RESOLVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load canonical verified authorization resolver")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


resolver_module = _load_resolver_module()
authorization_contract = resolver_module.authorization_contract


class ReceiptDeliveryError(ValueError):
    """Fail-closed delivery error carrying a stable refusal code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeliveryOutcome:
    """Sanitized delivery result. Carries no signature or target material."""

    authorization_ref: str
    sequence: int
    accepted: bool
    duplicate: bool


def _normalized(name: Any) -> str:
    return str(name).strip().lower().replace("-", "_")


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = _normalized(key)
            if normalized in FORBIDDEN_SECRET_FIELDS:
                raise ReceiptDeliveryError(
                    "DELIVERY_SECRET_MATERIAL_REFUSED",
                    "delivery envelope carries secret-shaped material",
                )
            if normalized in FORBIDDEN_TRUST_FIELDS:
                raise ReceiptDeliveryError(
                    "DELIVERY_TRUST_FIELD_REFUSED",
                    "caller may not assert trust or verification state",
                )
            _reject_forbidden_fields(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_fields(item)


def _trusted_audit_context(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or set(value) != AUDIT_CONTEXT_FIELDS:
        return None
    normalized: dict[str, str] = {}
    for key in AUDIT_CONTEXT_FIELDS:
        item = value.get(key)
        if not isinstance(item, str) or not item or len(item) > 256:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in item):
            return None
        normalized[key] = item
    return normalized


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["delivery policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.authorization.receipt-delivery":
        findings.append("policy_id must be hexor.runner.authorization.receipt-delivery")
    state = document.get("state")
    if state not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("delivery boundary must never claim execution authority")
    if document.get("issuer") != authorization_contract.ISSUER:
        findings.append(f"issuer must be {authorization_contract.ISSUER}")
    if document.get("runner_private_key") != "forbidden":
        findings.append("runner_private_key must be forbidden")
    if document.get("persistence") != "none":
        findings.append("delivery persistence must remain none in this lane")
    if document.get("restart_behaviour") != "fail-closed-empty":
        findings.append("restart_behaviour must be fail-closed-empty")

    channel = document.get("channel")
    if not isinstance(channel, Mapping):
        return findings + ["channel must be an object"]
    expected = {
        "kind",
        "transport",
        "socket_path",
        "allowed_peer_principal",
        "allowed_peer_uid",
        "require_monotonic_sequence",
    }
    if set(channel) != expected:
        findings.append("channel exact fields are required")
        return findings
    if channel.get("kind") != "local-authenticated":
        findings.append("channel kind must be local-authenticated")
    if channel.get("transport") != "af_unix-peercred":
        findings.append("channel transport must be af_unix-peercred")
    if channel.get("require_monotonic_sequence") is not True:
        findings.append("monotonic sequence enforcement is mandatory")

    socket_path = channel.get("socket_path")
    principal = channel.get("allowed_peer_principal")
    uid = channel.get("allowed_peer_uid")
    if state == "DISABLED":
        if socket_path != "NOT_CONFIGURED":
            findings.append("disabled delivery socket_path must be NOT_CONFIGURED")
        if principal != "NOT_CONFIGURED":
            findings.append("disabled delivery allowed_peer_principal must be NOT_CONFIGURED")
        if uid != -1:
            findings.append("disabled delivery allowed_peer_uid must be -1")
    elif state == "ENABLED":
        if not isinstance(socket_path, str) or not socket_path.startswith("/"):
            findings.append("enabled delivery socket_path must be absolute")
        if not isinstance(principal, str) or not principal or principal == "NOT_CONFIGURED":
            findings.append("enabled delivery allowed_peer_principal must be a real principal")
        if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
            findings.append("enabled delivery allowed_peer_uid must be a non-negative uid")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReceiptDeliveryError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise ReceiptDeliveryError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise ReceiptDeliveryError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class TrustedReceiptDelivery:
    """Authenticated local composition boundary in front of the resolver cache."""

    def __init__(
        self,
        policy: Mapping[str, Any],
        resolver: Any,
        audit_observer: Any | None = None,
    ) -> None:
        findings = validate_policy(policy)
        if findings:
            raise ReceiptDeliveryError("POLICY_INVALID", "; ".join(findings))
        if resolver is None or not hasattr(resolver, "register_receipt"):
            raise ReceiptDeliveryError(
                "RESOLVER_REQUIRED",
                "delivery requires a verified authorization resolver",
            )
        if audit_observer is not None:
            if not callable(getattr(audit_observer, "record_event", None)):
                raise ReceiptDeliveryError(
                    "AUDIT_OBSERVER_INVALID",
                    "delivery audit observer must expose record_event",
                )
            if not callable(getattr(resolver, "forget", None)):
                raise ReceiptDeliveryError(
                    "RESOLVER_ROLLBACK_REQUIRED",
                    "audited delivery requires resolver forget() rollback",
                )
        self._policy = dict(policy)
        self._channel = dict(policy["channel"])
        self._resolver = resolver
        self._audit_observer = audit_observer
        self._last_sequence: int | None = None
        self._delivered: dict[int, str] = {}

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    @property
    def last_sequence(self) -> int | None:
        return self._last_sequence

    def _authenticate_peer(self, peer: Any) -> None:
        if not isinstance(peer, Mapping) or set(peer) != PEER_FIELDS:
            raise ReceiptDeliveryError(
                "PEER_CREDENTIALS_REQUIRED",
                "delivery requires exact AF_UNIX peer credentials",
            )
        uid = peer.get("uid")
        principal = peer.get("principal")
        if isinstance(uid, bool) or not isinstance(uid, int):
            raise ReceiptDeliveryError("PEER_CREDENTIALS_REQUIRED", "peer uid must be an integer")
        if uid != self._channel["allowed_peer_uid"]:
            raise ReceiptDeliveryError("PEER_UID_UNAUTHORIZED", "peer uid is not the control plane")
        if principal != self._channel["allowed_peer_principal"]:
            raise ReceiptDeliveryError(
                "PEER_PRINCIPAL_UNAUTHORIZED",
                "peer principal is not the control plane",
            )

    def _audit(
        self,
        *,
        audit_context: Any,
        event_type: str,
        phase: str,
        decision: str,
        reason_code: str,
        authorization_ref: Any = None,
        duplicate: bool = False,
        verified: Any | None = None,
    ) -> bool:
        if self._audit_observer is None:
            return True
        context = _trusted_audit_context(audit_context)
        if context is None:
            return False
        try:
            self._audit_observer.record_event(
                context=context,
                event_type=event_type,
                phase=phase,
                decision=decision,
                reason_code=reason_code,
                authorization_ref=authorization_ref,
                duplicate=duplicate,
                capability_id=(
                    getattr(verified, "capability_id", None) if verified is not None else None
                ),
                intrusiveness_level=(
                    getattr(verified, "intrusiveness_level", None)
                    if verified is not None
                    else None
                ),
            )
        except Exception:  # noqa: BLE001 - audit failure must fail closed without leakage
            return False
        return True

    def _raise_refusal(
        self,
        error: ReceiptDeliveryError,
        *,
        audit_context: Any,
        phase: str = "DELIVERY",
    ) -> None:
        if not self._audit(
            audit_context=audit_context,
            event_type="REFUSED",
            phase=phase,
            decision="DENY",
            reason_code=error.code,
        ):
            raise ReceiptDeliveryError(
                "DELIVERY_AUDIT_FAILED",
                "receipt delivery refusal could not be audited safely",
            ) from error
        raise error

    def deliver(
        self,
        envelope: Any,
        *,
        peer: Any,
        audit_context: Any = None,
    ) -> DeliveryOutcome:
        """Authenticate the peer, verify/register, audit, then report acceptance."""

        if not self.enabled:
            raise ReceiptDeliveryError(
                "DELIVERY_DISABLED",
                "receipt delivery policy is disabled",
            )
        if self._audit_observer is not None and _trusted_audit_context(audit_context) is None:
            raise ReceiptDeliveryError(
                "DELIVERY_AUDIT_CONTEXT_REQUIRED",
                "audited receipt delivery requires trusted correlation context",
            )

        try:
            self._authenticate_peer(peer)

            if not isinstance(envelope, Mapping) or set(envelope) != ENVELOPE_FIELDS:
                raise ReceiptDeliveryError(
                    "DELIVERY_ENVELOPE_INVALID",
                    "delivery envelope exact fields are required",
                )
            _reject_forbidden_fields(envelope)

            if envelope.get("schema_version") != "1.0":
                raise ReceiptDeliveryError(
                    "DELIVERY_ENVELOPE_INVALID",
                    "unsupported delivery envelope schema_version",
                )
            if envelope.get("issuer") != authorization_contract.ISSUER:
                raise ReceiptDeliveryError(
                    "DELIVERY_ISSUER_UNAUTHORIZED",
                    "only Hermes/TB1 may deliver authorization receipts",
                )

            sequence = envelope.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
                raise ReceiptDeliveryError(
                    "DELIVERY_SEQUENCE_INVALID",
                    "delivery sequence must be a non-negative integer",
                )
            if self._last_sequence is not None and sequence <= self._last_sequence:
                known = self._delivered.get(sequence)
                if known is not None:
                    return DeliveryOutcome(
                        authorization_ref=known,
                        sequence=sequence,
                        accepted=True,
                        duplicate=True,
                    )
                raise ReceiptDeliveryError(
                    "DELIVERY_SEQUENCE_REPLAY",
                    "delivery sequence is not monotonically increasing",
                )

            receipt = envelope.get("receipt")
            if not isinstance(receipt, Mapping):
                raise ReceiptDeliveryError(
                    "DELIVERY_RECEIPT_INVALID",
                    "delivery envelope must carry a receipt object",
                )
        except ReceiptDeliveryError as exc:
            self._raise_refusal(exc, audit_context=audit_context, phase="DELIVERY")
            raise AssertionError("unreachable")  # pragma: no cover

        try:
            verified = self._resolver.register_receipt(receipt)
        except resolver_module.AuthorizationResolverError as exc:
            if not self._audit(
                audit_context=audit_context,
                event_type="REFUSED",
                phase="REGISTRATION",
                decision="DENY",
                reason_code=exc.code,
            ):
                raise ReceiptDeliveryError(
                    "DELIVERY_AUDIT_FAILED",
                    "receipt verification refusal could not be audited safely",
                ) from exc
            raise

        if not self._audit(
            audit_context=audit_context,
            event_type="REGISTERED",
            phase="REGISTRATION",
            decision="ACCEPT",
            reason_code="RECEIPT_VERIFIED",
            authorization_ref=verified.authorization_ref,
            duplicate=False,
            verified=verified,
        ):
            try:
                self._resolver.forget(verified.authorization_ref)
            except Exception:  # noqa: BLE001 - rollback best effort; outcome remains denied
                pass
            raise ReceiptDeliveryError(
                "DELIVERY_AUDIT_FAILED",
                "verified receipt registration could not be audited safely",
            )

        self._last_sequence = sequence
        self._delivered[sequence] = verified.authorization_ref
        return DeliveryOutcome(
            authorization_ref=verified.authorization_ref,
            sequence=sequence,
            accepted=True,
            duplicate=False,
        )

    def safe_state(self) -> dict[str, Any]:
        """Sanitized delivery state for observability. No receipt or key material."""

        return {
            "enabled": self.enabled,
            "issuer": self._policy["issuer"],
            "transport": self._channel["transport"],
            "last_sequence": self._last_sequence,
            "delivered_count": len(self._delivered),
            "persistence": self._policy["persistence"],
            "restart_behaviour": self._policy["restart_behaviour"],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        load_policy(args.policy)
    except ReceiptDeliveryError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK TB1 receipt delivery boundary policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
