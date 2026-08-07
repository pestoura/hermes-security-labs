from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"

COMPLETED = {"SVP2-A-01", "SVP2-A-03", "SVP2-J-01"}
IMPLEMENTING = {
    "SVP2-A-02",
    "SVP2-B-01",
    "SVP2-B-02",
    "SVP2-B-03",
    "SVP2-C-01",
    "SVP2-C-02",
    "SVP2-D-01",
    "SVP2-D-02",
    "SVP2-E-01",
    "SVP2-E-02",
    "SVP2-F-01",
    "SVP2-F-02",
    "SVP2-G-01",
    "SVP2-H-01",
    "SVP2-I-01",
    "SVP2-J-02",
    "SVP2-K-01",
    "SVP2-L-01",
}


def _epics():
    data = yaml.safe_load(BACKLOG.read_text(encoding="utf-8"))
    return {epic["id"]: epic for epic in data["epics"]}


def test_all_svp2_epics_are_reconciled_out_of_proposed() -> None:
    epics = _epics()
    assert set(epics) == COMPLETED | IMPLEMENTING
    assert {epic_id for epic_id, epic in epics.items() if epic["status"] == "completed"} == COMPLETED
    assert {epic_id for epic_id, epic in epics.items() if epic["status"] == "implementing"} == IMPLEMENTING
    assert all(epic["status"] != "proposed" for epic in epics.values())


def test_status_labels_match_machine_readable_status() -> None:
    for epic in _epics().values():
        status_labels = [label for label in epic["labels"] if label.startswith("status:")]
        assert status_labels == [f"status:{epic['status']}"]


def test_runtime_heavy_epics_are_not_falsely_completed() -> None:
    epics = _epics()
    runtime_heavy = {
        "SVP2-A-02",
        "SVP2-B-01",
        "SVP2-B-02",
        "SVP2-B-03",
        "SVP2-C-01",
        "SVP2-C-02",
        "SVP2-D-01",
        "SVP2-D-02",
        "SVP2-E-01",
        "SVP2-E-02",
        "SVP2-F-01",
        "SVP2-F-02",
        "SVP2-G-01",
        "SVP2-H-01",
        "SVP2-I-01",
        "SVP2-J-02",
        "SVP2-K-01",
        "SVP2-L-01",
    }
    assert all(epics[epic_id]["status"] == "implementing" for epic_id in runtime_heavy)
