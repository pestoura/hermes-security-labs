from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

QUERY_TYPES = {"entity", "relations", "applicability", "temporal_series"}
TEMPORAL_TYPES = {"epss", "kev", "vex"}
FORBIDDEN_PROPOSAL_FIELDS = {"command", "argv", "shell", "cwd", "environment", "executable", "entrypoint"}


class KnowledgeAPIError(ValueError):
    """Fail-closed Security Knowledge API contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_snapshot(*, source_record_ids: Iterable[str], created_at: str) -> dict[str, Any]:
    records = sorted(set(source_record_ids))
    if not records or any(not item.startswith("kr_") or len(item) != 35 for item in records):
        raise KnowledgeAPIError("snapshot requires valid knowledge record identifiers")
    if not created_at:
        raise KnowledgeAPIError("snapshot creation time is required")
    seed = {"source_record_ids": records, "created_at": created_at}
    snapshot_hash = _digest(seed)
    return {
        "schema_version": "1.0",
        "snapshot_id": f"ks_{snapshot_hash[:32]}",
        "created_at": created_at,
        "source_record_ids": records,
        "snapshot_sha256": snapshot_hash,
        "immutable": True,
    }


def validate_query(query: Mapping[str, Any]) -> None:
    if query.get("type") not in QUERY_TYPES:
        raise KnowledgeAPIError("unsupported knowledge query type")
    snapshot_id = query.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.startswith("ks_") or len(snapshot_id) != 35:
        raise KnowledgeAPIError("query requires an immutable snapshot identifier")
    minimum_confidence = query.get("minimum_confidence")
    if isinstance(minimum_confidence, bool) or not isinstance(minimum_confidence, (int, float)):
        raise KnowledgeAPIError("minimum confidence is required")
    if not 0.0 <= float(minimum_confidence) <= 1.0:
        raise KnowledgeAPIError("minimum confidence must be between 0 and 1")
    if query.get("type") == "temporal_series" and query.get("series") not in TEMPORAL_TYPES:
        raise KnowledgeAPIError("unsupported temporal series")


def filter_by_confidence(records: Iterable[Mapping[str, Any]], *, minimum_confidence: float) -> list[dict[str, Any]]:
    if not 0.0 <= minimum_confidence <= 1.0:
        raise KnowledgeAPIError("minimum confidence must be between 0 and 1")
    output: list[dict[str, Any]] = []
    for record in records:
        confidence = record.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            continue
        if float(confidence) >= minimum_confidence:
            output.append(deepcopy(dict(record)))
    return output


def temporal_entry(*, series: str, observed_at: str, value: Any, source_record_id: str) -> dict[str, Any]:
    if series not in TEMPORAL_TYPES:
        raise KnowledgeAPIError("unsupported temporal series")
    if not observed_at or not source_record_id.startswith("kr_"):
        raise KnowledgeAPIError("temporal observation requires time and provenance")
    return {
        "series": series,
        "observed_at": observed_at,
        "value": deepcopy(value),
        "source_record_id": source_record_id,
        "append_only": True,
    }


def bind_campaign_snapshot(*, campaign_id: str, snapshot_id: str) -> dict[str, str]:
    if not campaign_id or not snapshot_id.startswith("ks_"):
        raise KnowledgeAPIError("campaign and snapshot identifiers are required")
    return {"campaign_id": campaign_id, "knowledge_snapshot_id": snapshot_id}


def build_campaign_proposal(
    *,
    campaign_id: str,
    snapshot_id: str,
    rationale: str,
    proposed_steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    if not campaign_id or not snapshot_id.startswith("ks_") or not rationale:
        raise KnowledgeAPIError("proposal requires campaign, snapshot and rationale")
    normalized_steps: list[dict[str, Any]] = []
    for step in proposed_steps:
        forbidden = FORBIDDEN_PROPOSAL_FIELDS.intersection(step)
        if forbidden:
            raise KnowledgeAPIError("campaign proposals cannot contain execution-shaped fields")
        if not step.get("operation") or not step.get("reason"):
            raise KnowledgeAPIError("proposal steps require operation and reason")
        normalized_steps.append(deepcopy(dict(step)))
    if not normalized_steps:
        raise KnowledgeAPIError("proposal requires at least one step")
    return {
        "campaign_id": campaign_id,
        "knowledge_snapshot_id": snapshot_id,
        "rationale": rationale,
        "proposed_steps": normalized_steps,
        "proposal_state": "PROPOSAL_ONLY",
        "executable": False,
        "authorization_source": "CONTROL_PLANE_ONLY",
    }


def proposal_is_executable(proposal: Mapping[str, Any]) -> bool:
    return False
