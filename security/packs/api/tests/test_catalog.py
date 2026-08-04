from pathlib import Path

from api_pentest_runbooks.catalog import load_runbooks
from api_pentest_runbooks.validation import validate_repository

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_contains_exactly_150_unique_runbooks():
    runbooks = load_runbooks(ROOT / "runbooks")
    assert len(runbooks) == 150
    assert len({item["metadata"]["id"] for item in runbooks}) == 150


def test_all_runbooks_validate():
    assert validate_repository(ROOT) == []


def test_catalog_has_expected_category_distribution():
    runbooks = load_runbooks(ROOT / "runbooks")
    counts = {}
    for item in runbooks:
        category = item["metadata"]["category"]
        counts[category] = counts.get(category, 0) + 1
    assert counts == {
        "discovery": 12,
        "transport": 8,
        "authentication": 24,
        "authorization": 24,
        "token-session": 16,
        "input-validation": 26,
        "data-exposure": 10,
        "rate-resource": 10,
        "business-logic": 10,
        "configuration": 10,
    }
