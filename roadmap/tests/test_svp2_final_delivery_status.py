from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"
EPIC_09 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-09-exploitation-safety.md"
A02_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-A-02-completion-as-built.md"

COMPLETED = {"SVP2-A-01", "SVP2-A-02", "SVP2-A-03", "SVP2-J-01"}
IMPLEMENTING = {
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


def test_runtime_heavy_epics_without_done_evidence_are_not_falsely_completed() -> None:
    epics = _epics()
    runtime_heavy = {
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


def test_a02_delivery_completion_does_not_claim_epic09_finality() -> None:
    epic = _epics()["SVP2-A-02"]
    epic09 = EPIC_09.read_text(encoding="utf-8")
    completion = A02_COMPLETION.read_text(encoding="utf-8")

    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-A-02-completion-as-built.md" in epic["references"]

    assert "**AS_BUILT**" in epic09
    assert "| FINAL | no |" in epic09
    assert "deployed cancellation request dispatch to runtime Runner: `NOT_IMPLEMENTED` / `NOT_RUN`" in epic09
    assert "deployed/operational kill-switch drill evidence: `NOT_RUN`" in epic09

    assert "SVP2-A-02`: **candidate for `completed`**" in completion
    assert "EPIC-09 FINAL`: **`no`**" in completion
    assert "DOD-10" in completion
    assert "production-ready exploitation safety" in completion
