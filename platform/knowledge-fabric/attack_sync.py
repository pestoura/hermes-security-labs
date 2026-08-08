from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class AttackSyncError(ValueError):
    """Fail-closed ATT&CK dataset/version migration contract violation."""


DATASET_KEYS = {
    "schema_version",
    "dataset_id",
    "provider",
    "domain",
    "dataset_version",
    "published_at",
    "source_locator",
    "source_origin",
    "external_fetch",
    "techniques",
}
TECHNIQUE_KEYS = {
    "attack_id",
    "object_id",
    "name",
    "revoked",
    "deprecated",
    "replaced_by",
    "platforms",
}
MAPPING_KEYS = {
    "mapping_id",
    "knowledge_snapshot_id",
    "attack_dataset_id",
    "attack_id",
}

DOMAINS = {"enterprise-attack", "mobile-attack", "ics-attack"}
ATTACK_ID_RE = re.compile(r"^T[0-9]{4}(?:\.[0-9]{3})?$")
OBJECT_ID_RE = re.compile(
    r"^attack-pattern--[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-"
    r"[89ab][a-f0-9]{3}-[a-f0-9]{12}$"
)
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")
DATASET_ID_RE = re.compile(r"^attackds_[a-f0-9]{32}$")
MAPPING_ID_RE = re.compile(r"^map_[a-f0-9]{32}$")
SNAPSHOT_ID_RE = re.compile(r"^ks_[a-f0-9]{32}$")

MAX_TECHNIQUES = 5000
MAX_MAPPINGS = 10000

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
        raise AttackSyncError(
            f"{label} may not contain authority, execution or secret fields"
        )


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AttackSyncError(
            f"{label} fields mismatch: missing={missing}, extra={extra}"
        )


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AttackSyncError(f"{label} must be a date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AttackSyncError(
            f"{label} must be an ISO-8601 date-time"
        ) from exc
    if parsed.tzinfo is None:
        raise AttackSyncError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _version_tuple(version: str) -> tuple[int, int, int]:
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise AttackSyncError("ATT&CK dataset version must be numeric dotted form")
    parts = [int(part) for part in version.split(".")]
    return tuple((parts + [0, 0])[:3])


def _validate_technique(technique: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(technique, Mapping):
        raise AttackSyncError("ATT&CK technique must be an object")
    _reject_forbidden_fields(technique, "ATT&CK technique")
    _require_exact_keys(technique, TECHNIQUE_KEYS, "ATT&CK technique")

    attack_id = technique.get("attack_id")
    if not isinstance(attack_id, str) or not ATTACK_ID_RE.fullmatch(attack_id):
        raise AttackSyncError("invalid ATT&CK technique identifier")
    object_id = technique.get("object_id")
    if not isinstance(object_id, str) or not OBJECT_ID_RE.fullmatch(object_id):
        raise AttackSyncError("invalid ATT&CK STIX object identifier")
    name = technique.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AttackSyncError("ATT&CK technique name is required")
    if not isinstance(technique.get("revoked"), bool):
        raise AttackSyncError("revoked must be boolean")
    if not isinstance(technique.get("deprecated"), bool):
        raise AttackSyncError("deprecated must be boolean")

    replacement = technique.get("replaced_by")
    if replacement is not None and (
        not isinstance(replacement, str)
        or not ATTACK_ID_RE.fullmatch(replacement)
    ):
        raise AttackSyncError("replaced_by must be a canonical ATT&CK id or null")
    if replacement == attack_id:
        raise AttackSyncError("ATT&CK technique cannot replace itself")
    if replacement is not None and not (
        technique["revoked"] or technique["deprecated"]
    ):
        raise AttackSyncError(
            "replacement requires the source technique to be revoked or deprecated"
        )

    platforms = technique.get("platforms")
    if (
        not isinstance(platforms, list)
        or len(set(platforms)) != len(platforms)
        or any(not isinstance(item, str) or not item.strip() for item in platforms)
    ):
        raise AttackSyncError("platforms must be a unique list of non-empty strings")

    return {
        "attack_id": attack_id,
        "object_id": object_id,
        "name": name.strip(),
        "revoked": technique["revoked"],
        "deprecated": technique["deprecated"],
        "replaced_by": replacement,
        "platforms": sorted(platforms),
    }


def _validate_replacement_graph(techniques: Sequence[Mapping[str, Any]]) -> None:
    by_id = {item["attack_id"]: item for item in techniques}
    for technique in techniques:
        replacement = technique["replaced_by"]
        if replacement is not None and replacement not in by_id:
            raise AttackSyncError("replacement must reference a technique in the same dataset")

    for start in by_id:
        seen: set[str] = set()
        current = start
        while current in by_id and by_id[current]["replaced_by"] is not None:
            if current in seen:
                raise AttackSyncError("replacement graph contains a cycle")
            seen.add(current)
            current = by_id[current]["replaced_by"]
        if current in seen:
            raise AttackSyncError("replacement graph contains a cycle")


def _dataset_seed(
    *,
    provider: str,
    domain: str,
    dataset_version: str,
    published_at: str,
    source_locator: str,
    techniques: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "domain": domain,
        "dataset_version": dataset_version,
        "published_at": published_at,
        "source_locator": source_locator,
        "source_origin": "SUPPLIED_SNAPSHOT",
        "external_fetch": "NOT_PERFORMED",
        "techniques": list(techniques),
    }


def build_dataset(
    *,
    provider: str,
    domain: str,
    dataset_version: str,
    published_at: str,
    source_locator: str,
    techniques: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if provider != "MITRE ATT&CK":
        raise AttackSyncError("provider must be MITRE ATT&CK")
    if domain not in DOMAINS:
        raise AttackSyncError("unsupported ATT&CK domain")
    _version_tuple(dataset_version)
    _parse_utc(published_at, "published_at")
    if not isinstance(source_locator, str) or not source_locator.startswith("snapshot:"):
        raise AttackSyncError("source_locator must identify a supplied snapshot")
    if (
        not isinstance(techniques, Sequence)
        or isinstance(techniques, (str, bytes))
        or not techniques
        or len(techniques) > MAX_TECHNIQUES
    ):
        raise AttackSyncError("dataset requires a bounded non-empty technique set")

    normalized = [_validate_technique(item) for item in techniques]
    attack_ids = [item["attack_id"] for item in normalized]
    object_ids = [item["object_id"] for item in normalized]
    if len(set(attack_ids)) != len(attack_ids):
        raise AttackSyncError("ATT&CK technique identifiers must be unique")
    if len(set(object_ids)) != len(object_ids):
        raise AttackSyncError("ATT&CK STIX object identifiers must be unique")
    normalized.sort(key=lambda item: item["attack_id"])
    _validate_replacement_graph(normalized)

    seed = _dataset_seed(
        provider=provider,
        domain=domain,
        dataset_version=dataset_version,
        published_at=published_at,
        source_locator=source_locator,
        techniques=normalized,
    )
    return {
        "schema_version": "1.0",
        "dataset_id": f"attackds_{_digest(seed)[:32]}",
        **seed,
    }


def validate_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(dataset, Mapping):
        raise AttackSyncError("ATT&CK dataset must be an object")
    _reject_forbidden_fields(dataset, "ATT&CK dataset")
    _require_exact_keys(dataset, DATASET_KEYS, "ATT&CK dataset")
    if dataset.get("schema_version") != "1.0":
        raise AttackSyncError("unsupported ATT&CK dataset schema version")
    if dataset.get("provider") != "MITRE ATT&CK":
        raise AttackSyncError("provider must be MITRE ATT&CK")
    if dataset.get("domain") not in DOMAINS:
        raise AttackSyncError("unsupported ATT&CK domain")
    _version_tuple(dataset.get("dataset_version"))
    _parse_utc(dataset.get("published_at"), "published_at")
    source_locator = dataset.get("source_locator")
    if not isinstance(source_locator, str) or not source_locator.startswith("snapshot:"):
        raise AttackSyncError("source_locator must identify a supplied snapshot")
    if dataset.get("source_origin") != "SUPPLIED_SNAPSHOT":
        raise AttackSyncError("only supplied ATT&CK snapshots are supported")
    if dataset.get("external_fetch") != "NOT_PERFORMED":
        raise AttackSyncError("external fetch is outside this repository contract")

    techniques = dataset.get("techniques")
    if (
        not isinstance(techniques, list)
        or not techniques
        or len(techniques) > MAX_TECHNIQUES
    ):
        raise AttackSyncError("dataset requires a bounded non-empty technique set")
    normalized = [_validate_technique(item) for item in techniques]
    attack_ids = [item["attack_id"] for item in normalized]
    object_ids = [item["object_id"] for item in normalized]
    if len(set(attack_ids)) != len(attack_ids):
        raise AttackSyncError("ATT&CK technique identifiers must be unique")
    if len(set(object_ids)) != len(object_ids):
        raise AttackSyncError("ATT&CK STIX object identifiers must be unique")
    normalized.sort(key=lambda item: item["attack_id"])
    _validate_replacement_graph(normalized)

    seed = _dataset_seed(
        provider=dataset["provider"],
        domain=dataset["domain"],
        dataset_version=dataset["dataset_version"],
        published_at=dataset["published_at"],
        source_locator=dataset["source_locator"],
        techniques=normalized,
    )
    expected_id = f"attackds_{_digest(seed)[:32]}"
    dataset_id = dataset.get("dataset_id")
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id):
        raise AttackSyncError("invalid ATT&CK dataset id")
    if dataset_id != expected_id:
        raise AttackSyncError("dataset id does not match canonical dataset content")
    return {"schema_version": "1.0", "dataset_id": dataset_id, **seed}


def validate_mapping(mapping: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(mapping, Mapping):
        raise AttackSyncError("ATT&CK mapping must be an object")
    _reject_forbidden_fields(mapping, "ATT&CK mapping")
    _require_exact_keys(mapping, MAPPING_KEYS, "ATT&CK mapping")
    mapping_id = mapping.get("mapping_id")
    snapshot_id = mapping.get("knowledge_snapshot_id")
    dataset_id = mapping.get("attack_dataset_id")
    attack_id = mapping.get("attack_id")
    if not isinstance(mapping_id, str) or not MAPPING_ID_RE.fullmatch(mapping_id):
        raise AttackSyncError("invalid mapping id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise AttackSyncError("invalid knowledge snapshot id")
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id):
        raise AttackSyncError("invalid ATT&CK dataset id in mapping")
    if not isinstance(attack_id, str) or not ATTACK_ID_RE.fullmatch(attack_id):
        raise AttackSyncError("invalid ATT&CK id in mapping")
    return {
        "mapping_id": mapping_id,
        "knowledge_snapshot_id": snapshot_id,
        "attack_dataset_id": dataset_id,
        "attack_id": attack_id,
    }


def _change_reason(old: Mapping[str, Any], new: Mapping[str, Any] | None) -> str | None:
    if new is None:
        return "REMOVED"
    if new["revoked"] and not old["revoked"]:
        return "REVOKED"
    if new["deprecated"] and not old["deprecated"]:
        return "DEPRECATED"
    if new["replaced_by"] is not None and new["replaced_by"] != old["replaced_by"]:
        return "REPLACED"
    if new["name"] != old["name"]:
        return "RENAMED"
    if new["object_id"] != old["object_id"]:
        return "OBJECT_ID_CHANGED"
    return None


def build_migration_report(
    *,
    from_dataset: Mapping[str, Any],
    to_dataset: Mapping[str, Any],
    mappings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    old = validate_dataset(from_dataset)
    new = validate_dataset(to_dataset)
    if old["provider"] != new["provider"] or old["domain"] != new["domain"]:
        raise AttackSyncError("migration datasets must share provider and domain")
    if _version_tuple(new["dataset_version"]) <= _version_tuple(old["dataset_version"]):
        raise AttackSyncError("target ATT&CK dataset version must be newer")
    if _parse_utc(new["published_at"], "published_at") <= _parse_utc(
        old["published_at"], "published_at"
    ):
        raise AttackSyncError("target ATT&CK dataset publication must be newer")
    if (
        not isinstance(mappings, Sequence)
        or isinstance(mappings, (str, bytes))
        or len(mappings) > MAX_MAPPINGS
    ):
        raise AttackSyncError("mapping set exceeds the bounded contract")

    validated_mappings = [validate_mapping(item) for item in mappings]
    mapping_ids = [item["mapping_id"] for item in validated_mappings]
    if len(set(mapping_ids)) != len(mapping_ids):
        raise AttackSyncError("mapping ids must be unique")
    if any(item["attack_dataset_id"] != old["dataset_id"] for item in validated_mappings):
        raise AttackSyncError("historical mappings must reference the source dataset")

    old_by_id = {item["attack_id"]: item for item in old["techniques"]}
    new_by_id = {item["attack_id"]: item for item in new["techniques"]}

    added = sorted(set(new_by_id) - set(old_by_id))
    removed = sorted(set(old_by_id) - set(new_by_id))
    renamed: list[dict[str, str]] = []
    status_changed: list[dict[str, Any]] = []
    replacements: list[dict[str, str]] = []
    object_id_changed: list[dict[str, str]] = []

    for attack_id in sorted(set(old_by_id).intersection(new_by_id)):
        old_item = old_by_id[attack_id]
        new_item = new_by_id[attack_id]
        if old_item["name"] != new_item["name"]:
            renamed.append(
                {
                    "attack_id": attack_id,
                    "from_name": old_item["name"],
                    "to_name": new_item["name"],
                }
            )
        if (
            old_item["revoked"] != new_item["revoked"]
            or old_item["deprecated"] != new_item["deprecated"]
        ):
            status_changed.append(
                {
                    "attack_id": attack_id,
                    "from_revoked": old_item["revoked"],
                    "to_revoked": new_item["revoked"],
                    "from_deprecated": old_item["deprecated"],
                    "to_deprecated": new_item["deprecated"],
                }
            )
        if new_item["replaced_by"] is not None and (
            new_item["replaced_by"] != old_item["replaced_by"]
        ):
            replacements.append(
                {
                    "attack_id": attack_id,
                    "replaced_by": new_item["replaced_by"],
                }
            )
        if old_item["object_id"] != new_item["object_id"]:
            object_id_changed.append(
                {
                    "attack_id": attack_id,
                    "from_object_id": old_item["object_id"],
                    "to_object_id": new_item["object_id"],
                }
            )

    affected_mappings: list[dict[str, Any]] = []
    for mapping in sorted(validated_mappings, key=lambda item: item["mapping_id"]):
        old_item = old_by_id.get(mapping["attack_id"])
        if old_item is None:
            raise AttackSyncError("historical mapping references unknown source technique")
        new_item = new_by_id.get(mapping["attack_id"])
        reason = _change_reason(old_item, new_item)
        if reason is None:
            continue
        affected_mappings.append(
            {
                "mapping_id": mapping["mapping_id"],
                "knowledge_snapshot_id": mapping["knowledge_snapshot_id"],
                "attack_id": mapping["attack_id"],
                "reason": reason,
                "proposed_replacement": (
                    new_item["replaced_by"] if new_item is not None else None
                ),
                "action": "REVIEW_REQUIRED",
                "historical_rewrite": False,
            }
        )

    blocking_findings: list[dict[str, str]] = []
    for attack_id in removed:
        blocking_findings.append(
            {
                "code": "REMOVED_TECHNIQUE",
                "attack_id": attack_id,
                "message": "Technique is absent from the target supplied snapshot.",
            }
        )
    for item in object_id_changed:
        blocking_findings.append(
            {
                "code": "OBJECT_ID_CHANGED",
                "attack_id": item["attack_id"],
                "message": "Stable ATT&CK id points to a different STIX object id.",
            }
        )
    for item in status_changed:
        if item["to_revoked"] or item["to_deprecated"]:
            new_item = new_by_id[item["attack_id"]]
            if new_item["replaced_by"] is None:
                blocking_findings.append(
                    {
                        "code": "STATUS_CHANGE_WITHOUT_REPLACEMENT",
                        "attack_id": item["attack_id"],
                        "message": "Revoked/deprecated technique has no declared replacement.",
                    }
                )

    changes = {
        "added": added,
        "removed": removed,
        "renamed": renamed,
        "status_changed": status_changed,
        "replacements": replacements,
        "object_id_changed": object_id_changed,
    }
    decision = "REVIEW_REQUIRED" if affected_mappings or blocking_findings else "ELIGIBLE_FOR_REVIEW"
    body = {
        "schema_version": "1.0",
        "from_dataset_id": old["dataset_id"],
        "to_dataset_id": new["dataset_id"],
        "from_version": old["dataset_version"],
        "to_version": new["dataset_version"],
        "domain": old["domain"],
        "changes": changes,
        "affected_mappings": affected_mappings,
        "blocking_findings": blocking_findings,
        "adoption_decision": decision,
        "automatic_adoption": False,
        "historical_rewrite": False,
        "external_sync": "NOT_PERFORMED",
        "execution_authority": "NONE",
    }
    return {"report_id": f"attackmig_{_digest(body)[:32]}", **body}
