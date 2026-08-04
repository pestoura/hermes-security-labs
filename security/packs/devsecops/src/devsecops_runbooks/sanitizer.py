"""Secret sanitisation for DevSecOps evidence, stdout and stderr.

Rules:

* the WrongSecrets laboratory serves synthetic challenge values; even so they
  are treated as secrets and are never propagated to the result document;
* sanitisation is applied on the way out, not on the way in, so an adapter
  bug cannot leak material through an unexpected field;
* the sanitiser is deterministic: the same input always yields the same
  redacted output, which keeps results diffable.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

MAX_TEXT_BYTES = 8192

#: Keys whose value is always replaced, regardless of content.
SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "answer",
        "api_key",
        "apikey",
        "authorization",
        "challenge_value",
        "client_secret",
        "cookie",
        "credential",
        "flag",
        "id_token",
        "key",
        "passphrase",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "session",
        "set-cookie",
        "solution",
        "token",
    }
)

#: Patterns matched inside free text (tool stdout/stderr).
_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # key: value / key=value pairs using a sensitive key name
    re.compile(
        r"(?i)\b("
        + "|".join(sorted(re.escape(key) for key in SENSITIVE_KEYS))
        + r")\b\s*[:=]\s*\S+"
    ),
    # HTTP authorization headers
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
    # PEM blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # common high-entropy provider tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    # WrongSecrets synthetic markers must not be echoed verbatim either
    re.compile(r"(?i)\bwrongsecrets_synthetic_marker\S*"),
)


def _redact_key_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}={REDACTED}"


def sanitize_text(value: Any, max_bytes: int = MAX_TEXT_BYTES) -> str:
    """Return ``value`` as text with secret-like material removed and bounded."""

    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    for index, pattern in enumerate(_TEXT_PATTERNS):
        if index == 0:
            text = pattern.sub(_redact_key_value, text)
        else:
            text = pattern.sub(REDACTED, text)
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        encoded = encoded[:max_bytes]
        text = encoded.decode("utf-8", errors="ignore") + "…[TRUNCATED]"
    return text


def _is_sensitive_key(key: str) -> bool:
    normalised = key.strip().lower().replace("-", "_")
    if normalised in SENSITIVE_KEYS:
        return True
    return any(part in normalised.split("_") for part in ("secret", "token", "password", "key"))


def sanitize_value(key: str | None, value: Any) -> Any:
    """Sanitise a single value, using ``key`` to decide on full redaction."""

    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [sanitize_value(None, item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_text(value)


def sanitize_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitise a mapping, redacting sensitive keys and values."""

    return {str(key): sanitize_value(str(key), value) for key, value in data.items()}
