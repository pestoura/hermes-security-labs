from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"
EPIC_05 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-05-runner-protocol-v2.md"
EPIC_09 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-09-exploitation-safety.md"
COMPATIBILITY = ROOT / "platform" / "runner-protocol" / "compatibility.yaml"
A02_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-A-02-completion-as-built.md"
B02_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-B-02-completion-as-built.md"

COMPLETED = {"SVP2-A-01", "SVP2-A-02", "SVP2-A-03", "SVP2-B-02", "SVP2-J-01"}
IMPLEMENTING = {
    "SVP2-B-01",
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


def test_b02_delivery_completion_does_not_claim_epic05_finality_or_production_readiness() -> None:
    epic = _epics()["SVP2-B-02"]
    epic05 = EPIC_05.read_text(encoding="utf-8")
    compatibility = yaml.safe_load(COMPATIBILITY.read_text(encoding="utf-8"))
    completion = B02_COMPLETION.read_text(encoding="utf-8")

    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-B-02-completion-as-built.md" in epic["references"]

    assert "**AS_BUILT**" in epic05
    assert "| FINAL | no |" in epic05
    assert "`FINAL` remains false" in epic05

    assert compatibility["protocol"]["status"] == "contract_only"
    assert compatibility["cross_family_supervised_conformance"]["status"] == "PASS_SYNTHETIC_PROCESS"
    assert compatibility["cross_family_supervised_conformance"]["sandbox_status"] == "NOT_IMPLEMENTED"
    assert compatibility["cross_family_supervised_conformance"]["execution_integration"] == "NOT_RUN"
    assert compatibility["cross_family_supervised_conformance"]["promotion_status"] == "blocked"
    assert all(family["execution_integration"] == "NOT_RUN" for family in compatibility["runner_families"])
    assert all(family["promotion_status"] == "blocked" for family in compatibility["runner_families"])

    assert "SVP2-B-02`: **candidate for `completed`**" in completion
    assert "EPIC-05 FINAL`: **`no`**" in completion
    assert "production execution integration: **`NOT_RUN`**" in completion
    assert "sandbox: **`NOT_IMPLEMENTED`**" in completion
    assert "DOD-10" in completion
