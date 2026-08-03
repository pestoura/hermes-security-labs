import csv
from pathlib import Path

from api_pentest_runbooks.catalog import load_runbooks

ROOT = Path(__file__).resolve().parents[1]


def test_runbook_mapping_has_exactly_150_unique_entries() -> None:
    mapping_path = ROOT / "docs" / "api-runbook-mapping.csv"
    with mapping_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 150
    runbook_ids = [row["runbook_id"] for row in rows]
    assert len(set(runbook_ids)) == 150


def test_mapping_matches_catalog_runbooks() -> None:
    runbooks = load_runbooks(ROOT / "runbooks")
    mapping_ids = set()
    with (ROOT / "docs" / "api-runbook-mapping.csv").open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping_ids.add(row["runbook_id"])
    assert {item["metadata"]["id"] for item in runbooks} == mapping_ids
