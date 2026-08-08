from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/knowledge-api/operational_query.py"
spec = importlib.util.spec_from_file_location("operational_query_hardening_contract", MODULE_PATH)
assert spec and spec.loader
querymod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = querymod
spec.loader.exec_module(querymod)

SNAPSHOT = "ks_" + "a" * 32


def query_unvalidated():
    return querymod.build_query(
        question_id="ASSETS_UNVALIDATED_FOR_VULNERABILITY",
        knowledge_snapshot_id=SNAPSHOT,
        principal_id="analyst-01",
        minimum_confidence=0.7,
        parameters={"vulnerability_id": "CVE-2026-12345"},
    )


def test_negative_query_denies_when_required_validation_index_kind_is_not_authorized() -> None:
    access = querymod.build_access_policy(
        principal_id="analyst-01",
        allowed_asset_ids=["asset-web"],
        allowed_campaign_ids=[],
        allowed_index_kinds=["ASSET"],
        allow_unscoped_knowledge=False,
    )
    asset = querymod.build_index_entry(
        kind="ASSET",
        knowledge_snapshot_id=SNAPSHOT,
        asset_ids=["asset-web"],
        summary="sanitized asset metadata",
    )
    result = querymod.execute_query(
        query=query_unvalidated(), access_policy=access, sanitized_index=[asset]
    )
    assert result["access_decision"] == "DENY"
    assert result["items"] == []
    assert result["index_scope_ids"] == []
    assert result["evidence_scope_ids"] == []


def test_negative_query_limitation_records_supplied_authorized_scope_boundary() -> None:
    access = querymod.build_access_policy(
        principal_id="analyst-01",
        allowed_asset_ids=["asset-web"],
        allowed_campaign_ids=[],
        allowed_index_kinds=["ASSET", "VALIDATION"],
        allow_unscoped_knowledge=False,
    )
    asset = querymod.build_index_entry(
        kind="ASSET",
        knowledge_snapshot_id=SNAPSHOT,
        asset_ids=["asset-web"],
        summary="sanitized asset metadata",
    )
    result = querymod.execute_query(
        query=query_unvalidated(), access_policy=access, sanitized_index=[asset]
    )
    assert result["items"] == [{"asset_id": "asset-web"}]
    assert "NEGATIVE_RESULTS_ARE_LIMITED_TO_THE_SUPPLIED_AUTHORIZED_INDEX_SCOPE" in result["limitations"]
    assert "ABSENCE_OF_RESULTS_IS_NOT_A_PASS_VERDICT" in result["limitations"]


def test_semantic_index_shapes_fail_closed() -> None:
    with pytest.raises(querymod.OperationalQueryError, match="exactly one asset"):
        querymod.build_index_entry(
            kind="VALIDATION",
            knowledge_snapshot_id=SNAPSHOT,
            asset_ids=["asset-a", "asset-b"],
            vulnerability_ids=["CVE-2026-12345"],
            summary="sanitized validation metadata",
        )

    with pytest.raises(querymod.OperationalQueryError, match="requires technique and control"):
        querymod.build_index_entry(
            kind="CONTROL_MAPPING",
            knowledge_snapshot_id=SNAPSHOT,
            summary="sanitized mapping metadata",
        )

    with pytest.raises(querymod.OperationalQueryError, match="requires finding id"):
        querymod.build_index_entry(
            kind="FINDING",
            knowledge_snapshot_id=SNAPSHOT,
            asset_ids=["asset-web"],
            summary="sanitized finding metadata",
        )
