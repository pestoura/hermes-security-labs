"""Migrate API runbook evaluation sections to semantic signal criteria with provenance."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO_ROOT
RUNBOOKS_ROOT = PACK_ROOT / "runbooks"
CATALOG = yaml.safe_load((PACK_ROOT / "signals" / "signal-catalog.yaml").read_text(encoding="utf-8"))
SIGNALS = {name: value for name, value in (CATALOG.get("signals") or {}).items()}
BACKUP_DIR = PACK_ROOT / "dist" / "issue64-v3-backup"
MIGRATION_LOG = PACK_ROOT / "dist" / "issue64-v3-migration.csv"
HANDLER_FAMILIES: dict[str, tuple[str, ...]] = {
    "http": ("http", "openapi", "workflow", "headers", "race"),
    "openapi": ("http", "openapi", "workflow", "headers"),
    "tls": ("tls",),
    "nuclei": ("http", "nuclei", "workflow", "fuzz"),
    "sqlmap": ("http", "sqlmap", "workflow"),
    "jwt": ("jwt", "http"),
    "graphql": ("http", "graphql", "workflow"),
    "websocket": ("websocket", "workflow"),
    "fuzz": ("http", "fuzz", "workflow"),
    "race": ("http", "race", "workflow"),
    "headers": ("http", "headers", "workflow"),
    "workflow": ("workflow",),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _producers(signal: str) -> tuple[str, ...]:
    return tuple(SIGNALS.get(signal, {}).get("producer") or [])


def _allowed(handler: str, signal: str) -> bool:
    allowed = HANDLER_FAMILIES.get(handler, (handler,))
    return any(part in allowed for part in _producers(signal))


def _join_signals(items: list[str]) -> str:
    return " and ".join(items)


def _auth_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "jwt" in profile:
        return {
            "vulnerable_when": ["jwt_claims_aud is None or jwt_claims_aud not in {'hex0r-api','crapi'}"],
            "secure_when": ["jwt_claims_aud in {'hex0r-api','crapi'} and jwt_signature_valid == true"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "basic-transport" in profile:
        return {
            "vulnerable_when": ["auth_scheme == 'basic' and request_redirect_target != '' and request_redirect_target.startswith('http://')"],
            "secure_when": ["request_redirect_target == '' or request_redirect_target.startswith('https://')"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "missing-authentication" in profile or "user-enum" in profile or "apikey" in profile:
        return {
            "vulnerable_when": ["auth_accepted == false and response_status == 200"],
            "secure_when": ["auth_accepted == true or response_status in {401,403}"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "expired-token" in profile or "invalid-bearer" in profile or "unsigned-jwt" in profile:
        return {
            "vulnerable_when": ["response_status == 200 and auth_accepted == false"],
            "secure_when": ["response_status in {401,403}"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "lockout-bypass" in profile or "credential-rate" in profile:
        return {
            "vulnerable_when": ["race_duplicate_success == true"],
            "secure_when": ["race_duplicate_success == false"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return _inconclusive_only(runbook, "family_signal_producer_required")


def _authorization_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "vulnerable_when": ["object_owner_id != subject_id and subject_id != '' and response_status == 200"],
        "secure_when": ["object_owner_id == subject_id or subject_id == ''"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _token_session_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "cookie" in profile:
        return {
            "vulnerable_when": ["'secure' not in response_headers and 'httponly' not in response_headers"],
            "secure_when": ["'secure' in response_headers and 'httponly' in response_headers"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "jku" in profile or "jwk" in profile or "kid" in profile:
        return {
            "vulnerable_when": ["jwt_signature_valid == false"],
            "secure_when": ["jwt_signature_valid == true"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return {
        "vulnerable_when": ["jwt_claims_exp is None or jwt_claims_exp < prereq_now"],
        "secure_when": ["jwt_claims_exp is not None"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _transport_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "hsts" in profile:
        return {
            "vulnerable_when": ["'strict-transport-security' not in response_headers"],
            "secure_when": ["'strict-transport-security' in response_headers"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return {
        "vulnerable_when": ["tls_cert_expired == true or tls_hostname_mismatch == true or tls_weak_ciphers == true or tls_plaintext_allowed == true"],
        "secure_when": ["tls_cert_expired == false and tls_hostname_mismatch == false and tls_weak_ciphers == false and tls_plaintext_allowed == false"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _rate_resource_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "vulnerable_when": ["rate_limit_triggered == false and response_status == 200"],
        "secure_when": ["rate_limit_triggered == true"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _input_validation_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "ssrf" in profile:
        return {
            "vulnerable_when": ["request_redirect_target != '' and request_redirect_target.startswith('http://')"],
            "secure_when": ["request_redirect_target == '' or request_redirect_target.startswith('https://')"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    if "upload" in profile:
        return {
            "vulnerable_when": ["upload_executed == true"],
            "secure_when": ["upload_executed == false"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return {
        "vulnerable_when": ["response_status == 200 and response_contains_sensitive_data == true"],
        "secure_when": ["response_status in {400,401,403,404}"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _data_exposure_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "pii" in profile or "secret" in profile:
        return {
            "vulnerable_when": ["response_contains_sensitive_data == true"],
            "secure_when": ["response_contains_sensitive_data == false"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return {
        "vulnerable_when": ["response_status in {200,401,403,500} and response_contains_sensitive_data == true"],
        "secure_when": ["response_contains_sensitive_data == false"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _discovery_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "vulnerable_when": ["response_contains_schema == true or openapi_security_schemes_present == true"],
        "secure_when": ["response_contains_schema == false and openapi_security_schemes_present == false"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _business_logic_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "vulnerable_when": ["entity_id != '' and entity_owner_id != '' and entity_owner_id != subject_id"],
        "secure_when": ["entity_id == '' or entity_owner_id == '' or entity_owner_id == subject_id"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _configuration_criteria(runbook: dict[str, Any]) -> dict[str, list[str]]:
    profile = (runbook.get("steps", [{}])[0].get("profile") or "").lower()
    if "cors" in profile:
        return {
            "vulnerable_when": ["'access-control-allow-origin' in response_headers and 'access-control-allow-credentials' in response_headers"],
            "secure_when": ["'access-control-allow-origin' not in response_headers or 'access-control-allow-credentials' not in response_headers"],
            "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
        }
    return {
        "vulnerable_when": ["response_status in {200,401,403,500} and 'x-powered-by' in response_headers"],
        "secure_when": ["response_status in {401,403} or 'x-powered-by' not in response_headers"],
        "inconclusive_when": ["target_reachable == false or prerequisites_missing == true"],
    }


def _inconclusive_only(runbook: dict[str, Any], reason: str) -> dict[str, list[str]]:
    return {
        "vulnerable_when": [],
        "secure_when": [],
        "inconclusive_when": [
            "target_reachable == false or prerequisites_missing == true",
            reason,
        ],
    }


_CRITERIA_BUILDERS = {
    "authentication": _auth_criteria,
    "authorization": _authorization_criteria,
    "token-session": _token_session_criteria,
    "transport": _transport_criteria,
    "rate-resource": _rate_resource_criteria,
    "input-validation": _input_validation_criteria,
    "data-exposure": _data_exposure_criteria,
    "discovery": _discovery_criteria,
    "business-logic": _business_logic_criteria,
    "configuration": _configuration_criteria,
}


def migrate_runbook(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    original = yaml.safe_dump(data, sort_keys=False)
    category = str(data.get("metadata", {}).get("category") or "")
    handler = str((data.get("steps") or [{}])[0].get("handler") or "")
    criteria = _CRITERIA_BUILDERS.get(category, lambda r: _inconclusive_only(r, "unsupported_category"))(data)
    all_signals: set[str] = set()
    for key in ("vulnerable_when", "secure_when", "inconclusive_when"):
        for expr in criteria.get(key, []):
            for signal in _produced_signals_from_expr(expr):
                all_signals.add(signal)
    unsupported = [signal for signal in sorted(all_signals) if not _allowed(handler, signal)]
    if unsupported:
        criteria = _inconclusive_only(data, "family_signal_producer_required")
    data["evaluation"] = criteria
    updated = yaml.safe_dump(data, sort_keys=False)
    if original == updated:
        return {"runbook_id": data.get("metadata", {}).get("id"), "path": str(path), "status": "unchanged"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return {
        "runbook_id": data.get("metadata", {}).get("id"),
        "path": str(path),
        "status": "updated",
        "category": category,
        "handler": handler,
        "unsupported_signals": unsupported,
    }


def _produced_signals_from_expr(expr: str) -> list[str]:
    found = []
    for signal in SIGNALS:
        if signal in expr:
            found.append(signal)
    return found


def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_rows = [["runbook_id", "category", "handler", "status", "unsupported_signals"]]
    for path in sorted(RUNBOOKS_ROOT.rglob("*.yaml")):
        relative = path.relative_to(RUNBOOKS_ROOT)
        backup = BACKUP_DIR / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        result = migrate_runbook(path)
        log_rows.append([
            str(result.get("runbook_id") or ""),
            str(result.get("category") or ""),
            str(result.get("handler") or ""),
            str(result.get("status") or ""),
            ";".join(result.get("unsupported_signals") or []),
        ])
    with MIGRATION_LOG.open("w", encoding="utf-8", newline="") as handle:
        import csv
        writer = csv.writer(handle)
        writer.writerows(log_rows)
    print(f"MIGRATED: {len(log_rows)-1} runbooks -> {MIGRATION_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
