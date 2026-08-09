#!/usr/bin/env python3
"""Structured scenario evidence contract aligned with Evidence Plane v2.

This module validates declarations only. It does not read payloads, create evidence,
contact runtime services, or mutate state. Evidence Plane policy remains the authority
for classifications, correlation identifiers and integrity digest requirements.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVIDENCE_POLICY = ROOT / "platform" / "evidence-plane" / "evidence-policy.yaml"

CONTRACT_VERSION = "1.0"

# Semantic evidence types are deliberately limited to projections already supported by
# the execution evidence bridge. Payload types become raw Evidence Plane records only
# when payload projection is explicitly requested; manifest/summary are deterministic
# bridge projections.
EVIDENCE_TYPES: dict[str, dict[str, str]] = {
    "execution_manifest": {
        "classification": "restricted",
        "media_type": "application/json",
        "projection": "record",
    },
    "execution_summary": {
        "classification": "summary",
        "media_type": "application/json",
        "projection": "record",
    },
    "structured_result": {
        "classification": "raw",
        "media_type": "application/json",
        "projection": "payload",
    },
    "reset_attestation": {
        "classification": "raw",
        "media_type": "application/json",
        "projection": "payload",
    },
}


class EvidenceContractError(ValueError):
    """Fail-closed structured evidence contract violation."""


def load_policy(path: Path = EVIDENCE_POLICY) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvidenceContractError(f"evidence policy unavailable or invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceContractError("evidence policy must be a mapping")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{name} must be a mapping")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f"{name} must be a non-empty string")
    return value.strip()


def validate_contract(
    requirements: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and normalize one scenario evidence declaration against policy."""

    contract = _mapping(requirements, "evidence_requirements")
    expected_keys = {
        "contract_version",
        "evidence_plane_schema_version",
        "correlation",
        "integrity",
        "expected",
    }
    unknown = set(contract) - expected_keys
    missing = expected_keys - set(contract)
    if unknown:
        raise EvidenceContractError(f"unsupported evidence contract fields: {sorted(unknown)}")
    if missing:
        raise EvidenceContractError(f"missing evidence contract fields: {sorted(missing)}")

    if contract.get("contract_version") != CONTRACT_VERSION:
        raise EvidenceContractError(f"contract_version must be {CONTRACT_VERSION}")

    policy_doc = dict(policy) if policy is not None else load_policy()
    policy_schema = _string(policy_doc.get("schema_version"), "policy.schema_version")
    if contract.get("evidence_plane_schema_version") != policy_schema:
        raise EvidenceContractError(
            "evidence_plane_schema_version does not match Evidence Plane policy"
        )

    correlation = _mapping(contract.get("correlation"), "correlation")
    if set(correlation) != {"required_ids"}:
        raise EvidenceContractError("correlation must contain only required_ids")
    required_ids = correlation.get("required_ids")
    policy_ids = policy_doc.get("required_correlation_ids")
    if not isinstance(required_ids, list) or not required_ids:
        raise EvidenceContractError("correlation.required_ids must be a non-empty array")
    if not isinstance(policy_ids, list) or not policy_ids:
        raise EvidenceContractError("Evidence Plane policy correlation ids are missing")
    if required_ids != policy_ids:
        raise EvidenceContractError(
            "correlation.required_ids must exactly match Evidence Plane policy"
        )
    if len(set(required_ids)) != len(required_ids):
        raise EvidenceContractError("correlation.required_ids contains duplicates")

    integrity = _mapping(contract.get("integrity"), "integrity")
    if set(integrity) != {"digest"}:
        raise EvidenceContractError("integrity must contain only digest")
    policy_integrity = _mapping(policy_doc.get("required_integrity"), "policy.required_integrity")
    digest = _string(integrity.get("digest"), "integrity.digest")
    if digest != policy_integrity.get("digest"):
        raise EvidenceContractError("integrity.digest does not match Evidence Plane policy")

    policy_classes = policy_doc.get("classifications")
    if not isinstance(policy_classes, Mapping) or not policy_classes:
        raise EvidenceContractError("Evidence Plane policy classifications are missing")

    expected = contract.get("expected")
    if not isinstance(expected, list) or not expected:
        raise EvidenceContractError("expected must be a non-empty array")

    normalized_expected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(expected):
        item = _mapping(raw, f"expected[{index}]")
        if set(item) != {"evidence_type", "classification", "media_type", "required"}:
            raise EvidenceContractError(
                f"expected[{index}] must contain evidence_type, classification, media_type and required"
            )
        evidence_type = _string(item.get("evidence_type"), f"expected[{index}].evidence_type")
        if evidence_type in seen:
            raise EvidenceContractError(f"duplicate evidence_type: {evidence_type}")
        seen.add(evidence_type)
        type_contract = EVIDENCE_TYPES.get(evidence_type)
        if type_contract is None:
            raise EvidenceContractError(f"unsupported evidence_type: {evidence_type}")

        classification = _string(item.get("classification"), f"expected[{index}].classification")
        if classification not in policy_classes:
            raise EvidenceContractError(f"unsupported evidence classification: {classification}")
        if classification != type_contract["classification"]:
            raise EvidenceContractError(
                f"{evidence_type} classification must be {type_contract['classification']}"
            )

        media_type = _string(item.get("media_type"), f"expected[{index}].media_type")
        if media_type != type_contract["media_type"]:
            raise EvidenceContractError(
                f"{evidence_type} media_type must be {type_contract['media_type']}"
            )
        if item.get("required") is not True:
            raise EvidenceContractError(f"{evidence_type} must declare required: true")

        normalized_expected.append(
            {
                "evidence_type": evidence_type,
                "classification": classification,
                "media_type": media_type,
                "projection": type_contract["projection"],
                "required": True,
            }
        )

    mandatory = {"execution_manifest", "execution_summary"}
    missing_mandatory = sorted(mandatory - seen)
    if missing_mandatory:
        raise EvidenceContractError(
            f"missing mandatory Evidence Plane projections: {missing_mandatory}"
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "evidence_plane_schema_version": policy_schema,
        "correlation": {"required_ids": list(required_ids)},
        "integrity": {"digest": digest},
        "expected": normalized_expected,
    }


def validate_registry_document(
    scenario_doc: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deterministic findings for all scenario evidence contracts."""

    scenarios = scenario_doc.get("scenarios")
    if not isinstance(scenarios, list):
        return ["scenario registry scenarios must be an array"]
    policy_doc = deepcopy(dict(policy)) if policy is not None else load_policy()
    findings: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            findings.append("scenario entry must be a mapping")
            continue
        scenario_id = scenario.get("scenario_id", "<unknown>")
        try:
            validate_contract(scenario.get("evidence_requirements"), policy=policy_doc)
        except EvidenceContractError as exc:
            findings.append(f"scenario '{scenario_id}': {exc}")
    return findings
