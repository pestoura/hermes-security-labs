from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_chg098_runtime_evidence_binds_exact_functional_sha() -> None:
    data = yaml.safe_load(
        (ROOT / "roadmap/reconciliation/juice-shop-skeleton-CHG-HSL-098.yaml").read_text()
    )
    assert data["change_record"] == "CHG-HSL-098"
    assert data["functional_commit"] == "bd4a9bed8297a1182ef7461bd6c79f87e5ac0716"
    assert data["result"] == "PASS_EXACT_SHA_LAB_LIFECYCLE"
    assert data["runtime"]["kali_http_status"] == 200
    assert data["runtime"]["smoke_while_kali_connected"] == {
        "result": "EXPECTED_FAIL",
        "exit_code": 1,
    }
    assert all(data["zero_residue"].values())


def test_chg098_validation_campaign_and_change_record_are_linked() -> None:
    campaign = yaml.safe_load(
        (ROOT / "validation/VAL-HSL-JUICE-SHOP-SKELETON-RECONCILIATION.yaml").read_text()
    )
    change = yaml.safe_load((ROOT / "changes/CHG-HSL-098.yaml").read_text())
    observation = campaign["observations"][0]
    assert campaign["state"] == "PASSED"
    assert campaign["candidate"]["commit"] == "bd4a9bed8297a1182ef7461bd6c79f87e5ac0716"
    assert observation["id"] == change["source"]["observation"]
    assert observation["changeRecord"] == "CHG-HSL-098"
    assert change["source"]["campaign"] == campaign["id"]
    assert change["validation"]["runtime"] == "PASS"
    assert change["validation"]["regression"] == "PASS"
