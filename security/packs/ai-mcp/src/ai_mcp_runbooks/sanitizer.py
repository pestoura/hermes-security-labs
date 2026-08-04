"""Sanitisation of AI/MCP evidence, prompts and runtime responses.

Rules:

* prompt text, model/runtime responses and synthetic markers are never
  propagated to the result document; adapters report rule identifiers,
  counts, hashes and flags only;
* sanitisation is applied on the way out, so an adapter bug cannot leak
  material through an unexpected field;
* the sanitiser is deterministic: the same input always produces the same
  redacted output, which keeps results diffable.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

REDACTED = "[REDACTED]"

MAX_TEXT_BYTES = 4096

#: Keys whose value is always replaced, regardless of content.
SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "answer",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "completion",
        "cookie",
        "credential",
        "flag",
        "id_token",
        "injection_payload",
        "key",
        "marker",
        "message",
        "model_output",
        "passphrase",
        "password",
        "private_key",
        "prompt",
        "raw_response",
        "refresh_token",
        "response",
        "secret",
        "session",
        "set-cookie",
        "solution",
        "synthetic_marker",
        "token",
        "vulnerable_answer",
        "vulnerable_response",
    }
)

#: Patterns matched inside free text.
_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b("
        + "|".join(sorted(re.escape(key) for key in SENSITIVE_KEYS))
        + r")\b\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    # Phase 2 synthetic laboratory markers must never be echoed verbatim.
    re.compile(r"(?i)\b[A-Z0-9_]*SYNTHETIC[A-Z0-9_]*MARKER[A-Z0-9_]*\b"),
    re.compile(r"(?i)\bHERMES_PHASE2_[A-Z0-9_]+"),
    re.compile(r"(?i)\b[A-Z0-9_]{3,}_MARKER\b"),
)


def fingerprint(value: Any, length: int = 12) -> str:
    """Return a stable, non-reversible short digest for correlation only."""

    text = value if isinstance(value, str) else repr(value)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def _redact_key_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}={REDACTED}"


def sanitize_text(value: Any, max_bytes: int = MAX_TEXT_BYTES) -> str:
    """Return ``value`` as text with sensitive material removed and bounded."""

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
    parts = normalised.split("_")
    return any(part in parts for part in ("secret", "token", "password", "key", "prompt", "marker"))


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
