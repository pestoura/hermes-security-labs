from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/knowledge-api/operational_query.py"
SCHEMA_DIR = ROOT / "platform/knowledge-api"

spec = importlib.util.spec_from_file_location("operational_query_contract", MODULE_PATH)
assert spec and spec.loader
querymod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = querymod
spec.loader.exec_module(querymod)

SNAPSHOT = "ks_" + "a" * 32


def policy(**overrides):
    values = {
        "principal_id": "analyst-01",
        "allowed_asset_ids": ["asset-api", "asset-web"],
        "allowed_campaign_ids": ["campaign-01"],
        "allowed_index_kinds": ["ASSET", "CONTROL_MAPPING", "VALIDATION", "FINDING", "CAMPAIGN"],
        "allow_unscoped_knowledge": True,
    }
    values.update(overrides)
    return querymod.build_access_policy(**values)


def query(question_id: str, parameters: dict[str, str], **overrides):
    values = {
        "question_id": question_id,
        "knowledge_snapshot_id": SNAPSHOT,
        "principal_id": "analyst-01",
        "minimum_confidence": 0.7,
        "parameters": parameters,
    }
    values.update(overrides)
    return querymod.build_query(**values)


def entry(kind: str, name: str, **overrides):
    values = {
        "kind": kind,
        "knowledge_snapshot_id": SNAPSHOT,
        "asset_ids": [],
        "technique_ids": [],
        "vulnerability_ids": [],
        "control_ids": [],
        "campaign_id": None,
        "finding_id": None,
        "evidence_ids": [],
        "confidence": 0.9,
        "summary": f"sanitized-{name}",
    }
    values.update(overrides)
    return querymod.build_index_entry(**values)


def schema(name: str):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_question_catalogue_is_fixed_and_canonical() -> None:
    assert querymod.question_catalogue() == (
        "ASSETS_UNVALIDATED_FOR_VULNERABILITY",
        "CAMPAIGNS_USING_SNAPSHOT",
        "CONTROLS_FOR_TECHNIQUE",
        "FINDINGS_FOR_ASSET",
    )


def test_request_policy_index_and_result_validate_against_schemas() -> None:
    access = policy()
    request = query("CONTROLS_FOR_TECHNIQUE", {"technique_id": "T1190"})
    mapping = entry(
        "CONTROL_MAPPING", "control",
        technique_ids=["T1190"], control_ids=["AC-3"], evidence_ids=["ev_mapping_1"],
    )
    result = querymod.execute_query(query=request, access_policy=access, sanitized_index=[mapping])
    jsonschema.validate(access, schema("operational-query-access-policy.schema.json"))
    jsonschema.validate(request, schema("operational-query-request.schema.json"))
    jsonschema.validate(mapping, schema("operational-query-index.schema.json"))
    jsonschema.validate(result, schema("operational-query-result.schema.json"))
    querymod.validate_result(result)


def test_controls_for_technique_is_deterministic_and_confidence_filtered() -> None:
    request = query("CONTROLS_FOR_TECHNIQUE", {"technique_id": "T1190"})
    ac3 = entry("CONTROL_MAPPING", "a", technique_ids=["T1190"], control_ids=["AC-3"], evidence_ids=["ev_a"])
    si4 = entry("CONTROL_MAPPING", "b", technique_ids=["T1190"], control_ids=["SI-4"], evidence_ids=["ev_b"], confidence=0.8)
    low = entry("CONTROL_MAPPING", "low", technique_ids=["T1190"], control_ids=["AU-2"], confidence=0.2)
    result_a = querymod.execute_query(query=request, access_policy=policy(), sanitized_index=[si4, low, ac3])
    result_b = querymod.execute_query(query=request, access_policy=policy(), sanitized_index=[ac3, si4, low])
    assert result_a == result_b
    assert result_a["items"] == [{"control_id": "AC-3"}, {"control_id": "SI-4"}]
    assert result_a["evidence_scope_ids"] == ["ev_a", "ev_b"]


def test_unvalidated_assets_are_computed_only_inside_authorized_asset_scope() -> None:
    request = query("ASSETS_UNVALIDATED_FOR_VULNERABILITY", {"vulnerability_id": "CVE-2026-12345"})
    asset_api = entry("ASSET", "api", asset_ids=["asset-api"])
    asset_web = entry("ASSET", "web", asset_ids=["asset-web"])
    asset_other = entry("ASSET", "other", asset_ids=["asset-other"])
    validation_api = entry(
        "VALIDATION", "valid-api", asset_ids=["asset-api"],
        vulnerability_ids=["CVE-2026-12345"], evidence_ids=["ev_validation_api"],
    )
    result = querymod.execute_query(
        query=request, access_policy=policy(),
        sanitized_index=[asset_other, asset_web, validation_api, asset_api],
    )
    assert result["access_decision"] == "ALLOW"
    assert result["items"] == [{"asset_id": "asset-web"}]
    assert "asset-other" not in json.dumps(result)


def test_findings_and_campaigns_are_access_scoped() -> None:
    finding_request = query("FINDINGS_FOR_ASSET", {"asset_id": "asset-web"})
    finding = entry(
        "FINDING", "finding", asset_ids=["asset-web"], finding_id="finding-01",
        evidence_ids=["ev_finding_1"], confidence=0.95,
    )
    denied_finding = entry(
        "FINDING", "other", asset_ids=["asset-other"], finding_id="finding-99",
        evidence_ids=["ev_hidden"], confidence=0.99,
    )
    result = querymod.execute_query(
        query=finding_request, access_policy=policy(), sanitized_index=[denied_finding, finding]
    )
    assert [item["finding_id"] for item in result["items"]] == ["finding-01"]
    assert "finding-99" not in json.dumps(result)
    assert "ev_hidden" not in result["evidence_scope_ids"]

    campaign_request = query("CAMPAIGNS_USING_SNAPSHOT", {})
    campaign_allowed = entry("CAMPAIGN", "campaign", campaign_id="campaign-01")
    campaign_hidden = entry("CAMPAIGN", "hidden", campaign_id="campaign-99")
    campaign_result = querymod.execute_query(
        query=campaign_request, access_policy=policy(), sanitized_index=[campaign_hidden, campaign_allowed]
    )
    assert campaign_result["items"] == [{"campaign_id": "campaign-01"}]


def test_access_denial_returns_no_items_or_scope() -> None:
    request = query("FINDINGS_FOR_ASSET", {"asset_id": "asset-web"})
    finding = entry("FINDING", "finding", asset_ids=["asset-web"], finding_id="finding-01", evidence_ids=["ev_finding_1"])
    denied_policy = policy(allowed_asset_ids=[])
    result = querymod.execute_query(query=request, access_policy=denied_policy, sanitized_index=[finding])
    assert result["access_decision"] == "DENY"
    assert result["items"] == []
    assert result["index_scope_ids"] == []
    assert result["evidence_scope_ids"] == []


def test_unscoped_knowledge_requires_explicit_policy_permission() -> None:
    request = query("CONTROLS_FOR_TECHNIQUE", {"technique_id": "T1190"})
    mapping = entry("CONTROL_MAPPING", "control", technique_ids=["T1190"], control_ids=["AC-3"])
    result = querymod.execute_query(
        query=request,
        access_policy=policy(allow_unscoped_knowledge=False),
        sanitized_index=[mapping],
    )
    assert result["access_decision"] == "DENY"
    assert result["items"] == []


def test_snapshot_mixing_fails_closed() -> None:
    request = query("CAMPAIGNS_USING_SNAPSHOT", {})
    wrong = entry("CAMPAIGN", "wrong", campaign_id="campaign-01", knowledge_snapshot_id="ks_" + "b" * 32)
    with pytest.raises(querymod.OperationalQueryError, match="snapshot does not match"):
        querymod.execute_query(query=request, access_policy=policy(), sanitized_index=[wrong])


def test_raw_evidence_secret_and_execution_fields_fail_closed() -> None:
    request = query("FINDINGS_FOR_ASSET", {"asset_id": "asset-web"})
    finding = entry("FINDING", "finding", asset_ids=["asset-web"], finding_id="finding-01")
    tampered = deepcopy(finding)
    tampered["raw_evidence"] = "must-never-be-queryable"
    with pytest.raises(querymod.OperationalQueryError, match="raw, secret"):
        querymod.execute_query(query=request, access_policy=policy(), sanitized_index=[tampered])

    tampered_query = deepcopy(request)
    tampered_query["parameters"]["command"] = "forbidden"
    with pytest.raises(querymod.OperationalQueryError):
        querymod.execute_query(query=tampered_query, access_policy=policy(), sanitized_index=[])


def test_query_policy_index_and_result_tampering_fail_closed() -> None:
    access = policy()
    request = query("CONTROLS_FOR_TECHNIQUE", {"technique_id": "T1190"})
    mapping = entry("CONTROL_MAPPING", "control", technique_ids=["T1190"], control_ids=["AC-3"])

    bad_policy = deepcopy(access)
    bad_policy["allow_unscoped_knowledge"] = False
    with pytest.raises(querymod.OperationalQueryError, match="policy id"):
        querymod.execute_query(query=request, access_policy=bad_policy, sanitized_index=[mapping])

    bad_query = deepcopy(request)
    bad_query["minimum_confidence"] = 0.2
    with pytest.raises(querymod.OperationalQueryError, match="query id"):
        querymod.execute_query(query=bad_query, access_policy=access, sanitized_index=[mapping])

    bad_index = deepcopy(mapping)
    bad_index["control_ids"] = ["AU-2"]
    with pytest.raises(querymod.OperationalQueryError, match="index id"):
        querymod.execute_query(query=request, access_policy=access, sanitized_index=[bad_index])

    result = querymod.execute_query(query=request, access_policy=access, sanitized_index=[mapping])
    bad_result = deepcopy(result)
    bad_result["items"] = [{"control_id": "AU-2"}]
    with pytest.raises(querymod.OperationalQueryError, match="result id"):
        querymod.validate_result(bad_result)


def test_results_never_claim_pass_compliance_assurance_execution_or_raw_evidence() -> None:
    request = query("CONTROLS_FOR_TECHNIQUE", {"technique_id": "T1190"})
    result = querymod.execute_query(query=request, access_policy=policy(), sanitized_index=[])
    assert result["items"] == []
    assert result["raw_evidence_exposed"] is False
    assert result["assurance_effect"] == "NONE"
    assert result["compliance_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"
    assert "ABSENCE_OF_RESULTS_IS_NOT_A_PASS_VERDICT" in result["limitations"]
    encoded_keys = json.dumps(result, sort_keys=True).lower()
    assert '"pass"' not in encoded_keys
    assert '"compliant"' not in encoded_keys
    assert '"certified"' not in encoded_keys
