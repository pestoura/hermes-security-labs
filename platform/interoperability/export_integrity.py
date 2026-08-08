"""Integrity binding for interoperability export signatures."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ExportIntegrityError(ValueError):
    pass


def payload_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_signature_binding(
    *,
    payload: Mapping[str, Any],
    signature_evidence: Mapping[str, Any],
) -> str:
    digest = payload_sha256(payload)
    claimed = signature_evidence.get("payload_sha256")
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        raise ExportIntegrityError("SIGNATURE_PAYLOAD_DIGEST_REQUIRED")
    if claimed != digest:
        raise ExportIntegrityError("SIGNATURE_PAYLOAD_DIGEST_MISMATCH")
    if signature_evidence.get("verified") is not True:
        raise ExportIntegrityError("SIGNATURE_NOT_VERIFIED")
    if not signature_evidence.get("signer") or not signature_evidence.get("algorithm"):
        raise ExportIntegrityError("SIGNATURE_METADATA_INCOMPLETE")
    return digest
