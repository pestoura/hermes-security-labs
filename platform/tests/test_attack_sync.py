from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "attack_sync.py"
DATASET_SCHEMA = ROOT / "knowledge-fabric" / "attack-dataset.schema.json"
REPORT_SCHEMA = ROOT / "knowledge-fabric" / "attack-migration-report.schema.json"

spec = importlib.util.spec_from_file_location("attack_sync", MODULE_PATH)
assert spec and spec.loader
attack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(attack)

SNAPSHOT = "ks_" + "a" * 32
MAPPING_1 = "map_" + "1" * 32
MAPPING_2 = "map_" + "2" * 32


def _object_id(value: int) -> str:
    return f"attack-pattern--00000000-0000-4000-8000-{value:012x}"


def _technique(
    attack_id: str,
    name: str,
    object_number: int,
    *,
    revoked: bool = False,
    deprecated: bool = False,
    replaced_by: str | None = None,
    platforms: list[str] | None = None,
) -> dict:
    return {
        "attack_id": attack_id,
        "object_id": _object_id(object_number),
        "name": name,
        "revoked": revoked,
        "deprecated": deprecated,
        "replaced_by": replaced_by,
        "platforms": platforms or ["Linux"],
    }


def _dataset(version: str, published: str, techniques: list[dict]) -> dict:
    return attack.build_dataset(
        provider="MITRE ATT&CK",
        domain="enterprise-attack",
        dataset_version=version,
        published_at=published,
        source_locator=f"snapshot:enterprise-attack-v{version}",
        techniques=techniques,
    )


def _baseline() -> dict:
    return _dataset(
        "16.0",
        "2026-01-01T00:00:00Z",
        [
            _technique("T1001", "Data Obfuscation", 1),
            _technique("T1002", "Legacy Technique", 2),
            _technique("T1003", "Credential Dumping", 3),
        ],
    )


def _target() -> dict:
    return _dataset(
        "17.0",
        "2026-06-01T00:00:00Z",
        [
            _technique("T1001", "Data Obfuscation Updated", 1),
            _technique(
                "T1002",
                "Legacy Technique",
                2,
                deprecated=True,
                replaced_by="T2002",
            ),
            _technique("T1003", "Credential Dumping", 30),
            _technique("T2002", "Replacement Technique", 4),
            _technique("T3003", "New Technique", 5),
        ],
    )


def _mapping(mapping_id: str, dataset_id: str, attack_id: str) -> dict:
    return {
        "mapping_id": mapping_id,
        "knowledge_snapshot_id": SNAPSHOT,
        "attack_dataset_id": dataset_id,
        "attack_id": attack_id,
    }


def test_dataset_and_report_validate_against_strict_schemas() -> None:
    dataset_schema = json.loads(DATASET_SCHEMA.read_text(encoding="utf-8"))
    report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    old = _baseline()
    new = _target()
    jsonschema.validate(old, dataset_schema)
    jsonschema.validate(new, dataset_schema)

    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=new,
        mappings=[_mapping(MAPPING_1, old["dataset_id"], "T1002")],
    )
    jsonschema.validate(report, report_schema)


def test_dataset_identity_is_deterministic_independent_of_technique_order() -> None:
    techniques = [
        _technique("T1001", "One", 1),
        _technique("T1002", "Two", 2),
    ]
    forward = _dataset("16.0", "2026-01-01T00:00:00Z", techniques)
    reverse = _dataset("16.0", "2026-01-01T00:00:00Z", list(reversed(techniques)))
    assert forward == reverse


def test_dataset_contract_is_supplied_snapshot_only() -> None:
    dataset = _baseline()
    assert dataset["source_origin"] == "SUPPLIED_SNAPSHOT"
    assert dataset["external_fetch"] == "NOT_PERFORMED"
    assert dataset["source_locator"].startswith("snapshot:")

    forged = deepcopy(dataset)
    forged["external_fetch"] = "PERFORMED"
    with pytest.raises(attack.AttackSyncError, match="external fetch"):
        attack.validate_dataset(forged)


def test_replacement_requires_deprecated_or_revoked_source() -> None:
    with pytest.raises(attack.AttackSyncError, match="replacement requires"):
        _dataset(
            "16.0",
            "2026-01-01T00:00:00Z",
            [
                _technique("T1001", "One", 1, replaced_by="T1002"),
                _technique("T1002", "Two", 2),
            ],
        )


def test_replacement_target_must_exist_in_same_dataset() -> None:
    with pytest.raises(attack.AttackSyncError, match="same dataset"):
        _dataset(
            "16.0",
            "2026-01-01T00:00:00Z",
            [
                _technique(
                    "T1001",
                    "One",
                    1,
                    deprecated=True,
                    replaced_by="T9999",
                )
            ],
        )


def test_replacement_cycles_fail_closed() -> None:
    with pytest.raises(attack.AttackSyncError, match="cycle"):
        _dataset(
            "16.0",
            "2026-01-01T00:00:00Z",
            [
                _technique(
                    "T1001",
                    "One",
                    1,
                    deprecated=True,
                    replaced_by="T1002",
                ),
                _technique(
                    "T1002",
                    "Two",
                    2,
                    deprecated=True,
                    replaced_by="T1001",
                ),
            ],
        )


def test_migration_requires_strictly_newer_version_and_publication() -> None:
    old = _baseline()
    same_version = _dataset(
        "16.0",
        "2026-06-01T00:00:00Z",
        old["techniques"],
    )
    with pytest.raises(attack.AttackSyncError, match="version must be newer"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=same_version,
            mappings=[],
        )

    newer_version_older_date = _dataset(
        "17.0",
        "2025-12-31T00:00:00Z",
        old["techniques"],
    )
    with pytest.raises(attack.AttackSyncError, match="publication must be newer"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=newer_version_older_date,
            mappings=[],
        )


def test_migration_detects_renames_status_replacements_additions_and_object_id_change() -> None:
    old = _baseline()
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=[],
    )
    assert report["changes"]["added"] == ["T2002", "T3003"]
    assert report["changes"]["removed"] == []
    assert report["changes"]["renamed"] == [
        {
            "attack_id": "T1001",
            "from_name": "Data Obfuscation",
            "to_name": "Data Obfuscation Updated",
        }
    ]
    assert report["changes"]["replacements"] == [
        {"attack_id": "T1002", "replaced_by": "T2002"}
    ]
    assert report["changes"]["object_id_changed"][0]["attack_id"] == "T1003"


def test_affected_mapping_is_review_only_and_history_is_never_rewritten() -> None:
    old = _baseline()
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=[_mapping(MAPPING_1, old["dataset_id"], "T1002")],
    )
    assert report["affected_mappings"] == [
        {
            "mapping_id": MAPPING_1,
            "knowledge_snapshot_id": SNAPSHOT,
            "attack_id": "T1002",
            "reason": "DEPRECATED",
            "proposed_replacement": "T2002",
            "action": "REVIEW_REQUIRED",
            "historical_rewrite": False,
        }
    ]
    assert report["adoption_decision"] == "REVIEW_REQUIRED"
    assert report["automatic_adoption"] is False
    assert report["historical_rewrite"] is False


def test_unaffected_migration_is_still_not_automatically_adopted() -> None:
    old = _baseline()
    new = _dataset(
        "17.0",
        "2026-06-01T00:00:00Z",
        old["techniques"],
    )
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=new,
        mappings=[],
    )
    assert report["adoption_decision"] == "ELIGIBLE_FOR_REVIEW"
    assert report["automatic_adoption"] is False
    assert report["historical_rewrite"] is False
    assert report["external_sync"] == "NOT_PERFORMED"
    assert report["execution_authority"] == "NONE"


def test_removed_technique_is_a_blocking_finding() -> None:
    old = _baseline()
    new = _dataset(
        "17.0",
        "2026-06-01T00:00:00Z",
        [
            _technique("T1001", "Data Obfuscation", 1),
            _technique("T1003", "Credential Dumping", 3),
        ],
    )
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=new,
        mappings=[_mapping(MAPPING_1, old["dataset_id"], "T1002")],
    )
    assert report["changes"]["removed"] == ["T1002"]
    assert report["blocking_findings"][0]["code"] == "REMOVED_TECHNIQUE"
    assert report["affected_mappings"][0]["reason"] == "REMOVED"


def test_deprecated_without_replacement_is_blocking() -> None:
    old = _baseline()
    new = _dataset(
        "17.0",
        "2026-06-01T00:00:00Z",
        [
            _technique("T1001", "Data Obfuscation", 1),
            _technique("T1002", "Legacy Technique", 2, deprecated=True),
            _technique("T1003", "Credential Dumping", 3),
        ],
    )
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=new,
        mappings=[],
    )
    assert any(
        item["code"] == "STATUS_CHANGE_WITHOUT_REPLACEMENT"
        and item["attack_id"] == "T1002"
        for item in report["blocking_findings"]
    )


def test_object_id_change_is_blocking() -> None:
    old = _baseline()
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=[_mapping(MAPPING_1, old["dataset_id"], "T1003")],
    )
    assert any(
        item["code"] == "OBJECT_ID_CHANGED" and item["attack_id"] == "T1003"
        for item in report["blocking_findings"]
    )
    assert report["affected_mappings"][0]["reason"] == "OBJECT_ID_CHANGED"


def test_mapping_must_reference_source_dataset_and_known_source_technique() -> None:
    old = _baseline()
    new = _target()
    with pytest.raises(attack.AttackSyncError, match="source dataset"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=new,
            mappings=[_mapping(MAPPING_1, new["dataset_id"], "T1001")],
        )
    with pytest.raises(attack.AttackSyncError, match="unknown source technique"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=new,
            mappings=[_mapping(MAPPING_1, old["dataset_id"], "T9999")],
        )


def test_report_is_deterministic_independent_of_mapping_order() -> None:
    old = _baseline()
    mappings = [
        _mapping(MAPPING_1, old["dataset_id"], "T1001"),
        _mapping(MAPPING_2, old["dataset_id"], "T1002"),
    ]
    forward = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=mappings,
    )
    reverse = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=list(reversed(mappings)),
    )
    assert forward == reverse


def test_cross_domain_migration_is_rejected() -> None:
    old = _baseline()
    new = attack.build_dataset(
        provider="MITRE ATT&CK",
        domain="mobile-attack",
        dataset_version="17.0",
        published_at="2026-06-01T00:00:00Z",
        source_locator="snapshot:mobile-attack-v17.0",
        techniques=[_technique("T1001", "One", 1)],
    )
    with pytest.raises(attack.AttackSyncError, match="provider and domain"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=new,
            mappings=[],
        )


def test_authority_or_secret_fields_fail_closed() -> None:
    dataset = _baseline()
    forged = deepcopy(dataset)
    forged["authorization_ref"] = "forbidden"
    with pytest.raises(attack.AttackSyncError, match="authority"):
        attack.validate_dataset(forged)

    mapping = _mapping(MAPPING_1, dataset["dataset_id"], "T1001")
    mapping["token"] = "forbidden"
    with pytest.raises(attack.AttackSyncError, match="authority"):
        attack.validate_mapping(mapping)


def test_duplicate_mapping_ids_fail_closed() -> None:
    old = _baseline()
    duplicate = _mapping(MAPPING_1, old["dataset_id"], "T1001")
    with pytest.raises(attack.AttackSyncError, match="mapping ids must be unique"):
        attack.build_migration_report(
            from_dataset=old,
            to_dataset=_target(),
            mappings=[duplicate, deepcopy(duplicate)],
        )


def test_report_never_grants_execution_authority() -> None:
    old = _baseline()
    report = attack.build_migration_report(
        from_dataset=old,
        to_dataset=_target(),
        mappings=[],
    )
    assert report["automatic_adoption"] is False
    assert report["historical_rewrite"] is False
    assert report["external_sync"] == "NOT_PERFORMED"
    assert report["execution_authority"] == "NONE"
