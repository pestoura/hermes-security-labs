import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EPIC_04 = ROOT / "docs/roadmap/epics/EPIC-04-transactional-lifecycle-and-isolation.md"
EPIC_08 = ROOT / "docs/roadmap/epics/EPIC-08-network-and-egress-policy.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-04-08-transactional-lifecycle-contract-candidate-as-built.md"
README = ROOT / "platform/lab-lifecycle/README.md"
POLICY = ROOT / "platform/lab-lifecycle/lifecycle-policy.yaml"
ORPHAN_CODE = ROOT / "platform/lab-lifecycle/orphan_detector.py"
ORPHAN_OBSERVATION_SCHEMA = ROOT / "platform/lab-lifecycle/orphan-observation.schema.json"
ORPHAN_ASSESSMENT_SCHEMA = ROOT / "platform/lab-lifecycle/orphan-assessment.schema.json"


def test_concept_epics_are_implementing_but_not_final() -> None:
    for path in (EPIC_04, EPIC_08):
        text = path.read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        tail = text.split("## 14. Implementation notes", 1)[1]
        assert "Reserved" in tail
        assert "PR #139" in text
        assert "591552d652fbff82d81f750535799380e9c643a9" in text
        assert "31135492132" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_concept_epics_record_controlled_runtime_evidence_without_production_promotion() -> None:
    epic_04 = EPIC_04.read_text(encoding="utf-8")
    epic_08 = EPIC_08.read_text(encoding="utf-8")

    for text in (epic_04, epic_08):
        assert "`PASS_CONTROLLED_CI`" in text
        assert "periodic orphan" in text
        assert "orphan" in text and "remediation" in text
        assert "`NOT_RUN`" in text
        assert "NO_RUNTIME_CHANGE" in text

    assert "orphan observation/assessment contract and decision logic: `CANDIDATE`" in epic_04
    assert "controlled Docker CI network/volume scanner: `PASS_CONTROLLED_CI`" in epic_04
    assert "bounded periodic orphan scans: `PASS_CONTROLLED_CI`" in epic_04
    assert "controlled owned network/volume cleanup and zero-residue observation: `PASS_CONTROLLED_CI`" in epic_04
    assert "production/container scanner and lifecycle integration: `NOT_RUN`" in epic_04
    assert "real snapshot/rollback execution: `NOT_RUN`" in epic_04

    assert "effective network observation decision logic: `CANDIDATE`" in epic_08
    assert "controlled Docker CI internal-network observation: `PASS_CONTROLLED_CI`" in epic_08
    assert "controlled owned network/volume scanner: `PASS_CONTROLLED_CI`" in epic_08
    assert "bounded periodic orphan/network scans: `PASS_CONTROLLED_CI`" in epic_08
    assert "production scanner identity and firewall/exception enforcement: `NOT_RUN`" in epic_08


def test_supplementary_record_never_claims_runtime_or_final() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    assert "AS_BUILT — contract candidate" in text
    assert "| FINAL | no |" in text
    assert "Docker lifecycle integration: `NOT_RUN`" in text
    assert "network-policy enforcement: `NOT_RUN`" in text
    assert "zero-residue observation against real resources: `NOT_RUN`" in text
    assert "runtime resource scanner: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "periodic orphan scan scheduler: `NOT_IMPLEMENTED`" in text
    assert "orphan cleanup/remediation: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text
    assert "Canonical epic lifecycle" in text
    assert "`IMPLEMENTING`" in text
    assert "31135492132" in text
    assert "success" in text


def test_supplementary_record_references_every_lifecycle_component() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    for path in (
        "lab-lifecycle-contract.schema.json",
        "lab-transition-request.schema.json",
        "zero-residue-proof.schema.json",
        "lifecycle-policy.yaml",
        "lifecycle_protocol.py",
        "orphan-observation.schema.json",
        "orphan-assessment.schema.json",
        "orphan_detector.py",
        "test_lab_lifecycle_protocol.py",
        "test_lab_orphan_detector.py",
    ):
        assert path in text


def test_readme_preserves_unimplemented_runtime_boundaries() -> None:
    text = README.read_text(encoding="utf-8")

    assert "orphan observation/assessment contract and decision logic: `CANDIDATE`" in text
    assert "runtime resource scanner: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "periodic orphan scan scheduler: `NOT_IMPLEMENTED`" in text
    assert "orphan cleanup/remediation: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "Docker lifecycle integration: `NOT_RUN`" in text
    assert "network-policy enforcement: `NOT_RUN`" in text
    assert "zero-residue observation against real resources: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_orphan_assessor_has_no_runtime_or_cleanup_dependencies() -> None:
    tree = ast.parse(ORPHAN_CODE.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert imported_roots.isdisjoint(
        {"docker", "kubernetes", "subprocess", "socket", "requests", "httpx"}
    )
    assert called_names.isdisjoint(
        {
            "remove",
            "unlink",
            "rmdir",
            "rmtree",
            "kill",
            "terminate",
            "stop",
            "delete",
            "exec",
            "run",
            "Popen",
        }
    )


def test_orphan_contract_is_read_only_and_opaque() -> None:
    observation = ORPHAN_OBSERVATION_SCHEMA.read_text(encoding="utf-8")
    assessment = ORPHAN_ASSESSMENT_SCHEMA.read_text(encoding="utf-8")

    assert '"cleanup_performed": {"const": false}' in assessment
    assert '"PARTIAL"' in observation
    assert '"UNAVAILABLE"' in observation
    assert '"resource_ref"' in observation
    assert '"command"' not in observation
    assert '"target"' not in observation
    assert '"credential"' not in observation
    assert '"cleanup_performed": {"const": true}' not in assessment


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
