from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
SAFE_FIELD_CLASSIFICATIONS = {"public", "operational"}
SENSITIVE_FIELD_CLASSIFICATIONS = {
    "secret",
    "credential",
    "token",
    "cookie",
    "personal_data",
    "customer_data",
    "raw_command",
    "raw_output",
}
FIELD_CLASSIFICATIONS = SAFE_FIELD_CLASSIFICATIONS | SENSITIVE_FIELD_CLASSIFICATIONS
SENSITIVE_NAMES = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "stdout",
    "stderr",
    "command",
    "argv",
}
SAFE_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
MAX_FIELDS = 128
MAX_DEPTH = 6
MAX_STRING_LENGTH = 4096


class RedactionError(ValueError):
    """Fail-closed structured-redaction violation."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _validate_safe_value(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise RedactionError("field value exceeds maximum nesting depth")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise RedactionError("field string exceeds maximum length")
        return
    if isinstance(value, list):
        if len(value) > 128:
            raise RedactionError("field list exceeds maximum length")
        for item in value:
            _validate_safe_value(item, depth=depth + 1)
        return
    if isinstance(value, Mapping):
        if len(value) > 128:
            raise RedactionError("field object exceeds maximum size")
        for key, item in value.items():
            if not isinstance(key, str) or not SAFE_FIELD_NAME.fullmatch(key):
                raise RedactionError("nested field key is invalid")
            if _normalize_name(key) in SENSITIVE_NAMES:
                raise RedactionError("sensitive nested field name cannot be retained")
            _validate_safe_value(item, depth=depth + 1)
        return
    raise RedactionError("unsupported field value type")


def redact_structured_payload(payload: bytes, *, policy_id: str = "structured-label-v1") -> tuple[bytes, dict[str, Any]]:
    """Derive a deterministic sanitized payload from explicitly classified fields.

    The function does not attempt heuristic secret discovery. It retains only fields
    explicitly classified as safe and additionally denies sensitive field names even
    when a caller mislabels them. Unknown shapes/classifications fail closed.
    """
    try:
        source = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RedactionError("payload must be UTF-8 JSON") from exc
    if not isinstance(source, dict) or set(source) != {"schema_version", "fields"}:
        raise RedactionError("payload must use the canonical structured-redaction envelope")
    if source["schema_version"] != SCHEMA_VERSION:
        raise RedactionError("unsupported structured-redaction schema version")
    fields = source["fields"]
    if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
        raise RedactionError("fields must be a bounded list")

    retained: list[dict[str, Any]] = []
    removed_classes: set[str] = set()
    removed_fields: list[str] = []
    names: set[str] = set()

    for field in fields:
        if not isinstance(field, dict) or set(field) != {"name", "classification", "value"}:
            raise RedactionError("each field must have exactly name, classification and value")
        name = field["name"]
        classification = field["classification"]
        if not isinstance(name, str) or not SAFE_FIELD_NAME.fullmatch(name):
            raise RedactionError("invalid field name")
        if name in names:
            raise RedactionError("duplicate field name")
        names.add(name)
        if classification not in FIELD_CLASSIFICATIONS:
            raise RedactionError("unsupported field classification")

        normalized = _normalize_name(name)
        if classification in SENSITIVE_FIELD_CLASSIFICATIONS or normalized in SENSITIVE_NAMES:
            removed_fields.append(name)
            removed_classes.add(
                classification if classification in SENSITIVE_FIELD_CLASSIFICATIONS else "sensitive_name_override"
            )
            continue

        _validate_safe_value(field["value"])
        retained.append({"name": name, "value": field["value"]})

    retained.sort(key=lambda item: item["name"])
    sanitized = {"schema_version": SCHEMA_VERSION, "fields": retained}
    sanitized_bytes = _canonical_bytes(sanitized)
    metadata = {
        "policy_id": policy_id,
        "source_sha256": sha256_hex(payload),
        "removed_classes": sorted(removed_classes),
        "removed_fields": sorted(removed_fields),
        "retained_fields": [item["name"] for item in retained],
        "mode": "label_and_sensitive_name_fail_closed",
    }
    return sanitized_bytes, metadata
