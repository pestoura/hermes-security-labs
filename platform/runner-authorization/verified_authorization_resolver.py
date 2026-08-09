#!/usr/bin/env python3
"""Fail-closed Runner-side resolver for verified TB1 authorization references.

The resolver never issues authorization. Its only ingest path accepts a signed
TB1 receipt and delegates verification to the canonical authorization contract.
Only the sanitized ``VerifiedAuthorization`` result is cached in memory.

A naked authorization_ref is never sufficient: unknown, expired, disabled or
unverified references resolve to no authority.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = Path(__file__).resolve().parent / "resolver-policy.yaml"
AUTH_MODULE_PATH = ROOT / "platform" / "authorization-contract" / "authorization_receipt.py"
CANONICAL_VERIFICATION_SOURCE = "platform/authorization-contract/authorization_receipt.py"


def _load_authorization_module():
    name = "runner_verified_authorization_contract"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, AUTH_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load canonical TB1 authorization contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


authorization_contract = _load_authorization_module()
VerifiedAuthorization = authorization_contract.VerifiedAuthorization


class AuthorizationResolverError(ValueError):
    """Stable fail-closed authorization resolver error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise AuthorizationResolverError(
            "VERIFIED_AUTHORIZATION_INVALID",
            "verified authorization contains an invalid UTC timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationResolverError(
            "VERIFIED_AUTHORIZATION_INVALID",
            "verified authorization timestamp is not timezone-aware",
        )
    return parsed.astimezone(timezone.utc)


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["resolver policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.authorization.resolver":
        findings.append("policy_id must be hexor.runner.authorization.resolver")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("resolver must never claim execution authority")
    if document.get("verification_source") != CANONICAL_VERIFICATION_SOURCE:
        findings.append("verification_source must be the canonical TB1 verifier")

    trust_store = document.get("trust_store_path")
    state = document.get("state")
    if state == "DISABLED":
        if trust_store != "NOT_CONFIGURED":
            findings.append("disabled resolver trust_store_path must be NOT_CONFIGURED")
    elif state == "ENABLED":
        if not isinstance(trust_store, str) or not trust_store.startswith("/"):
            findings.append("enabled resolver trust_store_path must be absolute")

    cache = document.get("cache")
    if not isinstance(cache, Mapping):
        return findings + ["cache must be an object"]
    if set(cache) != {"mode", "max_entries", "persistence"}:
        findings.append("cache exact fields mode, max_entries, persistence are required")
    if cache.get("mode") != "memory-only":
        findings.append("cache mode must be memory-only in this lane")
    if cache.get("persistence") != "none":
        findings.append("cache persistence must remain none in this lane")
    max_entries = cache.get("max_entries")
    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or not 1 <= max_entries <= 4096:
        findings.append("cache max_entries must be an integer between 1 and 4096")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuthorizationResolverError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise AuthorizationResolverError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise AuthorizationResolverError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class VerifiedAuthorizationResolver:
    """Memory-only cache populated exclusively through canonical receipt verification."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise AuthorizationResolverError("POLICY_INVALID", "; ".join(findings))
        self._policy = dict(policy)
        self._entries: OrderedDict[str, Any] = OrderedDict()
        self._max_entries = int(policy["cache"]["max_entries"])

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    @property
    def size(self) -> int:
        return len(self._entries)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise AuthorizationResolverError(
                "RESOLVER_DISABLED",
                "authorization resolver policy is disabled",
            )

    def register_receipt(self, receipt: Mapping[str, Any]) -> Any:
        """Verify a signed TB1 receipt and cache sanitized metadata only."""

        self._require_enabled()
        trust_store = Path(str(self._policy["trust_store_path"]))
        try:
            verified = authorization_contract.verify_authorization_receipt(
                receipt,
                trust_store,
            )
        except authorization_contract.AuthorizationReceiptError as exc:
            raise AuthorizationResolverError(
                f"TB1_{exc.decision_code}",
                "TB1 receipt verification failed",
            ) from exc

        existing = self._entries.get(verified.authorization_ref)
        if existing is not None and existing != verified:
            raise AuthorizationResolverError(
                "AUTHORIZATION_REFERENCE_COLLISION",
                "authorization reference resolves to conflicting verified metadata",
            )
        if existing is not None:
            self._entries.move_to_end(verified.authorization_ref)
            return existing

        while len(self._entries) >= self._max_entries:
            self._entries.popitem(last=False)
        self._entries[verified.authorization_ref] = verified
        return verified

    def resolve(self, authorization_ref: str) -> Any | None:
        """Resolve only an already verified, still-live authorization reference."""

        if not self.enabled:
            return None
        if not isinstance(authorization_ref, str) or not authorization_ref.startswith(
            authorization_contract.AUTHORIZATION_REF_PREFIX
        ):
            return None
        verified = self._entries.get(authorization_ref)
        if verified is None:
            return None

        now = datetime.now(timezone.utc)
        try:
            issued_at = _parse_utc(verified.issued_at)
            expires_at = _parse_utc(verified.expires_at)
        except AuthorizationResolverError:
            self._entries.pop(authorization_ref, None)
            return None
        if now < issued_at or now >= expires_at:
            self._entries.pop(authorization_ref, None)
            return None

        self._entries.move_to_end(authorization_ref)
        return verified

    def forget(self, authorization_ref: str) -> bool:
        """Drop cached metadata. This revokes only local resolvability, not Hermes authority."""

        return self._entries.pop(authorization_ref, None) is not None

    def safe_inventory(self) -> list[dict[str, str]]:
        """Return sanitized cache metadata without target/parameter/signature material."""

        inventory: list[dict[str, str]] = []
        for verified in self._entries.values():
            inventory.append(
                {
                    "authorization_ref": verified.authorization_ref,
                    "campaign_id": verified.campaign_id,
                    "run_id": verified.run_id,
                    "step_id": verified.step_id,
                    "operation_id": verified.operation_id,
                    "capability_id": verified.capability_id,
                    "intrusiveness_level": verified.intrusiveness_level,
                    "expires_at": verified.expires_at,
                }
            )
        return inventory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        policy = load_policy(args.policy)
        VerifiedAuthorizationResolver(policy)
    except AuthorizationResolverError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK verified authorization resolver policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
