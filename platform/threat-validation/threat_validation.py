from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping

NODE_TYPES = {"asset", "identity", "trust", "credential", "vulnerability", "control", "evidence"}
EDGE_STATES = {"hypothetical", "evidenced"}
FORBIDDEN_PLAN_FIELDS = {"command", "argv", "shell", "credential_value", "secret", "token"}


class ThreatValidationError(ValueError):
    """Fail-closed threat-validation contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_threat_profile(
    *,
    critical_function: str,
    knowledge_snapshot_id: str,
    actor_refs: Iterable[str],
    objectives: Iterable[str],
) -> dict[str, Any]:
    actors = sorted(set(actor_refs))
    goals = sorted(set(objectives))
    if not critical_function or not knowledge_snapshot_id.startswith("ks_"):
        raise ThreatValidationError("critical function and knowledge snapshot are required")
    if not actors or not goals:
        raise ThreatValidationError("threat profile requires actors and objectives")
    seed = {
        "critical_function": critical_function,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "actor_refs": actors,
        "objectives": goals,
    }
    return {
        "schema_version": "1.0",
        "profile_id": f"tp_{_digest(seed)[:32]}",
        **seed,
        "executable": False,
    }


def build_emulation_plan(*, profile_id: str, critical_function: str, steps: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not profile_id.startswith("tp_") or not critical_function or not steps:
        raise ThreatValidationError("profile, critical function and steps are required")
    normalized: list[dict[str, Any]] = []
    for step in steps:
        if FORBIDDEN_PLAN_FIELDS.intersection(step):
            raise ThreatValidationError("emulation plans cannot contain execution or secret material")
        level = step.get("intrusiveness")
        if isinstance(level, bool) or not isinstance(level, int) or level not in range(5):
            raise ThreatValidationError("intrusiveness must be an integer from L0 to L4")
        if not step.get("objective") or not step.get("technique"):
            raise ThreatValidationError("emulation step requires objective and technique")
        normalized.append(deepcopy(dict(step)))
    return {
        "profile_id": profile_id,
        "critical_function": critical_function,
        "steps": normalized,
        "state": "PLAN_ONLY",
        "executable": False,
        "authorization_source": "CONTROL_PLANE_ONLY",
    }


def validate_graph(nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> None:
    node_list = [dict(node) for node in nodes]
    edge_list = [dict(edge) for edge in edges]
    node_ids = {node.get("id") for node in node_list}
    if None in node_ids or len(node_ids) != len(node_list):
        raise ThreatValidationError("graph node identifiers must be unique")
    for node in node_list:
        if node.get("type") not in NODE_TYPES:
            raise ThreatValidationError("unsupported attack-graph node type")
    for edge in edge_list:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            raise ThreatValidationError("edge must reference graph nodes")
        state = edge.get("state")
        if state not in EDGE_STATES:
            raise ThreatValidationError("edge state must be hypothetical or evidenced")
        evidence_ids = edge.get("evidence_ids", [])
        if state == "evidenced" and (not isinstance(evidence_ids, list) or not evidence_ids):
            raise ThreatValidationError("evidenced edge requires evidence identifiers")
        if state == "hypothetical" and evidence_ids:
            raise ThreatValidationError("hypothetical edge cannot claim evidence")


def find_paths(
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    *,
    start: str,
    end: str,
    evidenced_only: bool = False,
) -> list[list[str]]:
    node_list = [dict(node) for node in nodes]
    edge_list = [dict(edge) for edge in edges]
    validate_graph(node_list, edge_list)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edge_list:
        if evidenced_only and edge["state"] != "evidenced":
            continue
        adjacency[edge["from"]].append(edge["to"])
    paths: list[list[str]] = []

    def walk(current: str, path: list[str]) -> None:
        if current == end:
            paths.append(path.copy())
            return
        for candidate in adjacency.get(current, []):
            if candidate not in path:
                walk(candidate, path + [candidate])

    walk(start, [start])
    return paths


def degree_centrality(nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    node_list = [dict(node) for node in nodes]
    edge_list = [dict(edge) for edge in edges]
    validate_graph(node_list, edge_list)
    scores = {node["id"]: 0 for node in node_list}
    for edge in edge_list:
        scores[edge["from"]] += 1
        scores[edge["to"]] += 1
    return scores
