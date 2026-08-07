from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

import jsonschema

FORMATS = {"oscal-assessment-results", "oscal-poam", "cacao-2.0", "attack-flow"}


class InteroperabilityError(ValueError):
    """Fail-closed interoperability contract violation."""


def _payload_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_target_schema(*, payload: Mapping[str, Any], target_schema: Mapping[str, Any]) -> None:
    if not isinstance(target_schema, Mapping) or not target_schema:
        raise InteroperabilityError("explicit target schema is required")
    try:
        jsonschema.Draft202012Validator(target_schema).validate(dict(payload))
    except jsonschema.ValidationError as exc:
        raise InteroperabilityError("payload does not validate against target schema") from exc
    except jsonschema.SchemaError as exc:
        raise InteroperabilityError("target schema is invalid") from exc


def build_export(
    *,
    format_id: str,
    payload: Mapping[str, Any],
    target_schema: Mapping[str, Any],
    target_schema_id: str,
    target_schema_version: str,
    data_markings: list[str],
    signature_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if format_id not in FORMATS:
        raise InteroperabilityError("unsupported interoperability format")
    if not target_schema_id or not target_schema_version:
        raise InteroperabilityError("target schema identifier and version are required")
    if not data_markings or any(not marking for marking in data_markings):
        raise InteroperabilityError("data markings are required")
    if signature_evidence.get("verified") is not True:
        raise InteroperabilityError("verified signature evidence is required")
    if not signature_evidence.get("signer") or not signature_evidence.get("algorithm"):
        raise InteroperabilityError("signature signer and algorithm are required")
    validate_target_schema(payload=payload, target_schema=target_schema)
    return {
        "schema_version": "1.0",
        "format": format_id,
        "target_schema_id": target_schema_id,
        "target_schema_version": target_schema_version,
        "schema_validated": True,
        "data_markings": sorted(set(data_markings)),
        "signature": {
            "verified": True,
            "signer": str(signature_evidence["signer"]),
            "algorithm": str(signature_evidence["algorithm"]),
        },
        "payload_sha256": _payload_hash(payload),
        "payload": deepcopy(dict(payload)),
    }
