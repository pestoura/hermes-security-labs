from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class ControlKnowledgeError(ValueError):
    """Fail-closed control-knowledge contract violation."""


CATALOGUE_KEYS = {
    "schema_version",
    "catalogue_id",
    "provider",
    "catalogue_name",
    "catalogue_version",
    "published_at",
    "source_locator",
    "source_origin",
    "external_fetch",
    "controls",
}
CONTROL_KEYS = {
    "control_id",
    "title",
    "objective",
    "provenance_record_ids",
}
MAPPING_KEYS = {
    "schema_version",
    "mapping_id",
    "control_catalogue_id",
    "control_id",
    "target_kind",
    "target_ref",
    "confidence",
    "provenance_record_ids",
    "rationale",
}
OBSERVATION_KEYS = {
    "mapping_id",
    "state",
    "evidence_ids",
}

CONTROL_ID_RE = re.compile(r"^[A-Z]{2}-[0-9]+(?:\([0-9]+\))?$")
CATALOGUE_ID_RE = re.compile(r"^ctrlcat_[a-f0-9]{32}$")
MAPPING_ID_RE = re.compile(r"^ctrlmap_[a-f0-9]{32}$")
KNOWLEDGE_RECORD_RE = re.compile(r"^kr_[a-f0-9]{32}$")
EVIDENCE_ID_RE = re.compile(r"^ev_[a-f0-9]{32}$")
ATTACK_ID_RE = re.compile(r"^T[0-9]{4}(?:\.[0-9]{3})?$")
TARGET_KINDS = {"attack", "runbook", "evidence_requirement"}
OBSERVATION_STATES = {"OBSERVED", "NOT_OBSERVED", "NOT_RUN", "INCONCLUSIVE"}
PROJECTION_STATES = {
    "UNMAPPED",
    "MAPPED_NO_OBSERVATION",
    "MAPPED_EVIDENCE_PRESENT",
    "REVIEW_REQUIRED",
}
MAX_CONTROLS = 5000
MAX_MAPPINGS = 10000
MAX_PROVENANCE = 64
MAX_EVIDENCE = 256

FORBIDDEN_KEYS = {
    "authorization",
    "authorization_ref",
    "authorization_receipt",
    "authorization_receipt_ref",
    "execution_allowed",
    "execution_authorized",
    "roe_decision",
    "command",
    "argv",
    "shell",
    "payload",
    "credential",
    "secret",
    "token",
    "password",
    "cookie",
    "api_key",
    "compliant",
    "compliance_status",
    "certified",
    "certification_status",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


def _reject_forbidden_fields(value: Any, label: str) -> None:
    if _walk_keys(value).intersection(FORBIDDEN_KEYS):
        raise ControlKnowledgeError(
            f"{label} may not contain authority, execution, secret or compliance fields"
        )


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ControlKnowledgeError(
            f"{label} fields mismatch: missing={missing}, extra={extra}"
        )


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ControlKnowledgeError(f"{label} must be a date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlKnowledgeError(f"{label} must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ControlKnowledgeError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_provenance(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > MAX_PROVENANCE
        or len(set(value)) != len(value)
        or any(
            not isinstance(item, str) or not KNOWLEDGE_RECORD_RE.fullmatch(item)
            for item in value
        )
    ):
        raise ControlKnowledgeError(f"{label} requires unique knowledge-record provenance")
    return sorted(value)


def _validate_control(control: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(control, Mapping):
        raise ControlKnowledgeError("control must be an object")
    _reject_forbidden_fields(control, "control")
    _require_exact_keys(control, CONTROL_KEYS, "control")
    control_id = control.get("control_id")
    if not isinstance(control_id, str) or not CONTROL_ID_RE.fullmatch(control_id):
        raise ControlKnowledgeError("invalid NIST-style control identifier")
    title = control.get("title")
    objective = control.get("objective")
    if not isinstance(title, str) or not title.strip():
        raise ControlKnowledgeError("control title is required")
    if not isinstance(objective, str) or not objective.strip():
        raise ControlKnowledgeError("control objective is required")
    return {
        "control_id": control_id,
        "title": title.strip(),
        "objective": objective.strip(),
        "provenance_record_ids": _validate_provenance(
            control.get("provenance_record_ids"), "control"
        ),
    }


def _catalogue_seed(
    *,
    provider: str,
    catalogue_name: str,
    catalogue_version: str,
    published_at: str,
    source_locator: str,
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "catalogue_name": catalogue_name,
        "catalogue_version": catalogue_version,
        "published_at": published_at,
        "source_locator": source_locator,
        "source_origin": "SUPPLIED_SNAPSHOT",
        "external_fetch": "NOT_PERFORMED",
        "controls": list(controls),
    }


def build_catalogue(
    *,
    provider: str,
    catalogue_name: str,
    catalogue_version: str,
    published_at: str,
    source_locator: str,
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if provider != "NIST":
        raise ControlKnowledgeError("provider must be NIST")
    if not isinstance(catalogue_name, str) or not catalogue_name.strip():
        raise ControlKnowledgeError("catalogue name is required")
    if not isinstance(catalogue_version, str) or not catalogue_version.strip():
        raise ControlKnowledgeError("catalogue version is required")
    _parse_utc(published_at, "published_at")
    if not isinstance(source_locator, str) or not source_locator.startswith("snapshot:"):
        raise ControlKnowledgeError("source_locator must identify a supplied snapshot")
    if (
        not isinstance(controls, Sequence)
        or isinstance(controls, (str, bytes))
        or not controls
        or len(controls) > MAX_CONTROLS
    ):
        raise ControlKnowledgeError("catalogue requires a bounded non-empty control set")
    normalized = [_validate_control(item) for item in controls]
    control_ids = [item["control_id"] for item in normalized]
    if len(set(control_ids)) != len(control_ids):
        raise ControlKnowledgeError("control identifiers must be unique")
    normalized.sort(key=lambda item: item["control_id"])
    seed = _catalogue_seed(
        provider=provider,
        catalogue_name=catalogue_name.strip(),
        catalogue_version=catalogue_version.strip(),
        published_at=published_at,
        source_locator=source_locator,
        controls=normalized,
    )
    return {
        "schema_version": "1.0",
        "catalogue_id": f"ctrlcat_{_digest(seed)[:32]}",
        **seed,
    }


def validate_catalogue(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(catalogue, Mapping):
        raise ControlKnowledgeError("control catalogue must be an object")
    _reject_forbidden_fields(catalogue, "control catalogue")
    _require_exact_keys(catalogue, CATALOGUE_KEYS, "control catalogue")
    if catalogue.get("schema_version") != "1.0":
        raise ControlKnowledgeError("unsupported control catalogue schema version")
    if catalogue.get("provider") != "NIST":
        raise ControlKnowledgeError("provider must be NIST")
    if catalogue.get("source_origin") != "SUPPLIED_SNAPSHOT":
        raise ControlKnowledgeError("only supplied control snapshots are supported")
    if catalogue.get("external_fetch") != "NOT_PERFORMED":
        raise ControlKnowledgeError("external control fetch is outside this contract")
    _parse_utc(catalogue.get("published_at"), "published_at")
    if not isinstance(catalogue.get("source_locator"), str) or not catalogue[
        "source_locator"
    ].startswith("snapshot:"):
        raise ControlKnowledgeError("source_locator must identify a supplied snapshot")
    for field in ("catalogue_name", "catalogue_version"):
        if not isinstance(catalogue.get(field), str) or not catalogue[field].strip():
            raise ControlKnowledgeError(f"{field} is required")
    controls = catalogue.get("controls")
    if not isinstance(controls, list) or not controls or len(controls) > MAX_CONTROLS:
        raise ControlKnowledgeError("catalogue requires a bounded non-empty control set")
    normalized = [_validate_control(item) for item in controls]
    control_ids = [item["control_id"] for item in normalized]
    if len(set(control_ids)) != len(control_ids):
        raise ControlKnowledgeError("control identifiers must be unique")
    normalized.sort(key=lambda item: item["control_id"])
    seed = _catalogue_seed(
        provider=catalogue["provider"],
        catalogue_name=catalogue["catalogue_name"].strip(),
        catalogue_version=catalogue["catalogue_version"].strip(),
        published_at=catalogue["published_at"],
        source_locator=catalogue["source_locator"],
        controls=normalized,
    )
    catalogue_id = catalogue.get("catalogue_id")
    if not isinstance(catalogue_id, str) or not CATALOGUE_ID_RE.fullmatch(catalogue_id):
        raise ControlKnowledgeError("invalid control catalogue id")
    if catalogue_id != f"ctrlcat_{_digest(seed)[:32]}":
        raise ControlKnowledgeError("catalogue id does not match canonical content")
    return {"schema_version": "1.0", "catalogue_id": catalogue_id, **seed}


def _validate_target(kind: str, ref: Any) -> str:
    if kind not in TARGET_KINDS:
        raise ControlKnowledgeError("unsupported control mapping target kind")
    if not isinstance(ref, str) or not ref:
        raise ControlKnowledgeError("mapping target_ref is required")
    if kind == "attack" and not ATTACK_ID_RE.fullmatch(ref):
        raise ControlKnowledgeError("attack mapping requires canonical ATT&CK id")
    if kind == "runbook" and not re.fullmatch(r"runbook:[A-Za-z0-9._/-]+", ref):
        raise ControlKnowledgeError("runbook mapping requires runbook: reference")
    if kind == "evidence_requirement" and not re.fullmatch(
        r"evidence:[A-Za-z0-9._/-]+", ref
    ):
        raise ControlKnowledgeError("evidence mapping requires evidence: reference")
    return ref


def _validate_confidence(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ControlKnowledgeError("mapping confidence must be between 0 and 1")
    return float(value)


def build_mapping(
    *,
    catalogue: Mapping[str, Any],
    control_id: str,
    target_kind: str,
    target_ref: str,
    confidence: float,
    provenance_record_ids: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    validated_catalogue = validate_catalogue(catalogue)
    controls = {item["control_id"] for item in validated_catalogue["controls"]}
    if control_id not in controls:
        raise ControlKnowledgeError("mapping control is not present in catalogue")
    target = _validate_target(target_kind, target_ref)
    normalized_confidence = _validate_confidence(confidence)
    provenance = _validate_provenance(list(provenance_record_ids), "mapping")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ControlKnowledgeError("mapping rationale is required")
    seed = {
        "control_catalogue_id": validated_catalogue["catalogue_id"],
        "control_id": control_id,
        "target_kind": target_kind,
        "target_ref": target,
        "confidence": normalized_confidence,
        "provenance_record_ids": provenance,
        "rationale": rationale.strip(),
    }
    return {
        "schema_version": "1.0",
        "mapping_id": f"ctrlmap_{_digest(seed)[:32]}",
        **seed,
    }


def validate_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(mapping, Mapping):
        raise ControlKnowledgeError("control mapping must be an object")
    _reject_forbidden_fields(mapping, "control mapping")
    _require_exact_keys(mapping, MAPPING_KEYS, "control mapping")
    if mapping.get("schema_version") != "1.0":
        raise ControlKnowledgeError("unsupported control mapping schema version")
    mapping_id = mapping.get("mapping_id")
    catalogue_id = mapping.get("control_catalogue_id")
    control_id = mapping.get("control_id")
    if not isinstance(mapping_id, str) or not MAPPING_ID_RE.fullmatch(mapping_id):
        raise ControlKnowledgeError("invalid control mapping id")
    if not isinstance(catalogue_id, str) or not CATALOGUE_ID_RE.fullmatch(catalogue_id):
        raise ControlKnowledgeError("invalid control catalogue id in mapping")
    if not isinstance(control_id, str) or not CONTROL_ID_RE.fullmatch(control_id):
        raise ControlKnowledgeError("invalid control id in mapping")
    target_kind = mapping.get("target_kind")
    target_ref = _validate_target(target_kind, mapping.get("target_ref"))
    confidence = _validate_confidence(mapping.get("confidence"))
    provenance = _validate_provenance(mapping.get("provenance_record_ids"), "mapping")
    rationale = mapping.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ControlKnowledgeError("mapping rationale is required")
    seed = {
        "control_catalogue_id": catalogue_id,
        "control_id": control_id,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "confidence": confidence,
        "provenance_record_ids": provenance,
        "rationale": rationale.strip(),
    }
    if mapping_id != f"ctrlmap_{_digest(seed)[:32]}":
        raise ControlKnowledgeError("mapping id does not match canonical content")
    return {"schema_version": "1.0", "mapping_id": mapping_id, **seed}


def _validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ControlKnowledgeError("mapping observation must be an object")
    _reject_forbidden_fields(value, "mapping observation")
    _require_exact_keys(value, OBSERVATION_KEYS, "mapping observation")
    mapping_id = value.get("mapping_id")
    if not isinstance(mapping_id, str) or not MAPPING_ID_RE.fullmatch(mapping_id):
        raise ControlKnowledgeError("invalid mapping id in observation")
    state = value.get("state")
    if state not in OBSERVATION_STATES:
        raise ControlKnowledgeError("unsupported mapping observation state")
    evidence_ids = value.get("evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or len(evidence_ids) > MAX_EVIDENCE
        or len(set(evidence_ids)) != len(evidence_ids)
        or any(
            not isinstance(item, str) or not EVIDENCE_ID_RE.fullmatch(item)
            for item in evidence_ids
        )
    ):
        raise ControlKnowledgeError("evidence ids must be unique canonical evidence ids")
    if state == "OBSERVED" and not evidence_ids:
        raise ControlKnowledgeError("OBSERVED requires at least one evidence id")
    if state != "OBSERVED" and evidence_ids:
        raise ControlKnowledgeError("only OBSERVED may carry evidence ids")
    return {
        "mapping_id": mapping_id,
        "state": state,
        "evidence_ids": sorted(evidence_ids),
    }


def project_control(
    *,
    catalogue: Mapping[str, Any],
    control_id: str,
    mappings: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    minimum_confidence: float = 0.0,
) -> dict[str, Any]:
    validated_catalogue = validate_catalogue(catalogue)
    threshold = _validate_confidence(minimum_confidence)
    controls = {item["control_id"]: item for item in validated_catalogue["controls"]}
    if control_id not in controls:
        raise ControlKnowledgeError("projection control is not present in catalogue")
    if (
        not isinstance(mappings, Sequence)
        or isinstance(mappings, (str, bytes))
        or len(mappings) > MAX_MAPPINGS
    ):
        raise ControlKnowledgeError("mapping set exceeds the bounded contract")
    validated_mappings = [validate_mapping(item) for item in mappings]
    mapping_ids = [item["mapping_id"] for item in validated_mappings]
    if len(set(mapping_ids)) != len(mapping_ids):
        raise ControlKnowledgeError("mapping ids must be unique")
    if any(
        item["control_catalogue_id"] != validated_catalogue["catalogue_id"]
        for item in validated_mappings
    ):
        raise ControlKnowledgeError("all mappings must reference the supplied catalogue")

    control_mappings = sorted(
        [item for item in validated_mappings if item["control_id"] == control_id],
        key=lambda item: item["mapping_id"],
    )
    known_mapping_ids = {item["mapping_id"] for item in control_mappings}

    validated_observations = [_validate_observation(item) for item in observations]
    observation_ids = [item["mapping_id"] for item in validated_observations]
    if len(set(observation_ids)) != len(observation_ids):
        raise ControlKnowledgeError("at most one observation per mapping is allowed")
    if any(item["mapping_id"] not in known_mapping_ids for item in validated_observations):
        raise ControlKnowledgeError("observation references mapping outside projected control")
    by_mapping = {item["mapping_id"]: item for item in validated_observations}

    if not control_mappings:
        projection_state = "UNMAPPED"
        mapping_confidence = None
    else:
        mapping_confidence = min(item["confidence"] for item in control_mappings)
        observed = [
            by_mapping[item["mapping_id"]]
            for item in control_mappings
            if item["mapping_id"] in by_mapping
        ]
        if mapping_confidence < threshold or any(
            item["state"] in {"INCONCLUSIVE", "NOT_OBSERVED"} for item in observed
        ):
            projection_state = "REVIEW_REQUIRED"
        elif any(item["state"] == "OBSERVED" for item in observed):
            projection_state = "MAPPED_EVIDENCE_PRESENT"
        else:
            projection_state = "MAPPED_NO_OBSERVATION"

    evidence_ids = sorted(
        {
            evidence_id
            for observation in validated_observations
            for evidence_id in observation["evidence_ids"]
        }
    )
    body = {
        "schema_version": "1.0",
        "control_catalogue_id": validated_catalogue["catalogue_id"],
        "catalogue_version": validated_catalogue["catalogue_version"],
        "control_id": control_id,
        "projection_state": projection_state,
        "mapping_count": len(control_mappings),
        "mapping_confidence": mapping_confidence,
        "minimum_confidence": threshold,
        "mapping_ids": [item["mapping_id"] for item in control_mappings],
        "evidence_ids": evidence_ids,
        "coverage_semantics": "MAPPED_VALIDATION_COVERAGE_ONLY",
        "compliance_verdict": "NOT_EVALUATED",
        "certification_claim": "NONE",
        "planning_effect": "ADVISORY_ONLY",
        "execution_authority": "NONE",
        "limitations": [
            "MAPPING_DOES_NOT_ESTABLISH_COMPLIANCE",
            "EVIDENCE_DOES_NOT_ESTABLISH_CONTROL_EFFECTIVENESS_BY_ITSELF",
            "UNMAPPED_OR_UNOBSERVED_ARE_NOT_PASS_STATES",
        ],
    }
    return {"projection_id": f"ctrlproj_{_digest(body)[:32]}", **body}
