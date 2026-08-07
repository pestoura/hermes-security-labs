from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EPIC_04 = ROOT / "docs/roadmap/epics/EPIC-04-transactional-lifecycle-and-isolation.md"
EPIC_08 = ROOT / "docs/roadmap/epics/EPIC-08-network-and-egress-policy.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-04-08-transactional-lifecycle-contract-candidate-as-built.md"
README = ROOT / "platform/lab-lifecycle/README.md"
POLICY = ROOT / "platform/lab-lifecycle/lifecycle-policy.yaml"


def test_concept_epics_remain_intent_with_reserved_lifecycle_sections() -> None:
    for path in (EPIC_04, EPIC_08):
        text = path.read_text(encoding="utf-8")
        assert "**INTENT**" in text
        tail = text.split("## 14. Implementation notes", 1)[1]
        assert "Reserved" in tail
        assert "| FINAL | no |" in text


def test_supplementary_record_never_claims_runtime_or_final() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    assert "AS_BUILT — contract candidate" in text
    assert "| FINAL | no |" in text
    assert "Docker lifecycle integration: `NOT_RUN`" in text
    assert "network-policy enforcement: `NOT_RUN`" in text
    assert "zero-residue observation against real resources: `NOT_RUN`" in text
    assert "periodic orphan detector: `NOT_IMPLEMENTED`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_supplementary_record_references_every_lifecycle_component() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    for path in (
        "lab-lifecycle-contract.schema.json",
        "lab-transition-request.schema.json",
        "zero-residue-proof.schema.json",
        "lifecycle-policy.yaml",
        "lifecycle_protocol.py",
        "test_lab_lifecycle_protocol.py",
    ):
        assert path in text


def test_readme_preserves_unimplemented_runtime_boundaries() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Docker lifecycle integration: `NOT_RUN`" in text
    assert "network-policy enforcement: `NOT_RUN`" in text
    assert "zero-residue observation against real resources: `NOT_RUN`" in text
    assert "periodic orphan detector: `NOT_IMPLEMENTED`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_policy_defaults_to_isolated_and_quarantine_blocks_reuse() -> None:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))

    assert policy["default_network_profile"] == "isolated"
    assert policy["profiles"]["isolated"] == {
        "egress": "deny-all",
        "exceptions_allowed": False,
    }
    assert policy["state_transitions"]["QUARANTINED"] == []
    assert "QUARANTINED" in policy["blocked_reuse_states"]
    assert policy["runtime_status"] == "NOT_RUN"
