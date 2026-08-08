from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"
EPIC_05 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-05-runner-protocol-v2.md"
EPIC_06 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-06-kali-image-factory.md"
EPIC_09 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-09-exploitation-safety.md"
EPIC_10 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-10-evidence-plane.md"
EPIC_12 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-12-redaction-and-data-classification.md"
EPIC_36 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-36-security-knowledge-fabric.md"
COMPATIBILITY = ROOT / "platform" / "runner-protocol" / "compatibility.yaml"
RUNTIME_POLICY = ROOT / "platform" / "runtime-base" / "runtime-base-policy.yaml"
EVIDENCE_POLICY = ROOT / "platform" / "evidence-plane" / "evidence-policy.yaml"
KNOWLEDGE_SOURCE_POLICY = ROOT / "platform" / "knowledge-fabric" / "source-policy.yaml"
A02_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-A-02-completion-as-built.md"
B02_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-B-02-completion-as-built.md"
C01_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-C-01-completion-as-built.md"
D01_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-D-01-completion-as-built.md"
E01_COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-E-01-completion-as-built.md"

COMPLETED = {
    "SVP2-A-01", "SVP2-A-02", "SVP2-A-03", "SVP2-B-02", "SVP2-C-01",
    "SVP2-D-01", "SVP2-E-01", "SVP2-E-02", "SVP2-J-01",
}
IMPLEMENTING = {
    "SVP2-B-01",
    "SVP2-B-03",
    "SVP2-C-02",
    "SVP2-D-02",
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
        "SVP2-B-01", "SVP2-B-03", "SVP2-C-02", "SVP2-D-02",
        "SVP2-F-01", "SVP2-F-02", "SVP2-G-01", "SVP2-H-01", "SVP2-I-01",
        "SVP2-J-02", "SVP2-K-01", "SVP2-L-01",
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


def test_c01_delivery_completion_does_not_claim_epic06_or_supply_chain_finality() -> None:
    epic = _epics()["SVP2-C-01"]
    epic06 = EPIC_06.read_text(encoding="utf-8")
    policy = yaml.safe_load(RUNTIME_POLICY.read_text(encoding="utf-8"))
    completion = C01_COMPLETION.read_text(encoding="utf-8")
    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-C-01-completion-as-built.md" in epic["references"]
    assert "**IMPLEMENTING**" in epic06
    assert "| AS_BUILT | no |" in epic06
    assert "| FINAL | no |" in epic06
    assert policy["runtime_user"]["required_non_root"] is True
    assert policy["runtime_user"]["allow_uid_zero"] is False
    assert policy["capabilities"]["default_drop_all"] is True
    assert policy["capabilities"]["profiles"]["core"]["add"] == []
    assert policy["capabilities"]["profiles"]["core"]["nmap_default_mode"] == "-sT"
    raw_network = policy["capabilities"]["profiles"]["raw-network"]
    assert raw_network["add"] == ["NET_RAW"]
    assert raw_network["requires_explicit_profile"] is True
    assert raw_network["requires_justification"] is True
    assert policy["capabilities"]["profiles"]["privileged"]["allowed"] is False
    assert policy["runtime_status"] == {
        "image_build": "PASS_CONTROLLED_CI",
        "container_start": "PASS_CONTROLLED_CI",
        "non_root_observation": "PASS_CONTROLLED_CI",
        "read_only_root_observation": "PASS_CONTROLLED_CI",
        "capability_drop_observation": "PASS_CONTROLLED_CI",
    }
    assert policy["runtime_evidence"]["security_tool_execution"] == "NOT_RUN"
    assert policy["runtime_evidence"]["image_publication"] == "NOT_RUN"
    assert policy["runtime_evidence"]["hermes_deployment"] == "NOT_RUN"
    assert "SVP2-C-01`: **candidate for `completed`**" in completion
    assert "EPIC-06`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "image publication: **`NOT_RUN`**" in completion
    assert "SBOM/signing/provenance: **`NOT_RUN`**" in completion
    assert "Hermes deployment: **`NOT_RUN`**" in completion
    assert "DOD-10" in completion


def test_d01_delivery_completion_does_not_claim_epic10_or_epic12_finality() -> None:
    epic = _epics()["SVP2-D-01"]
    epic10 = EPIC_10.read_text(encoding="utf-8")
    epic12 = EPIC_12.read_text(encoding="utf-8")
    policy = yaml.safe_load(EVIDENCE_POLICY.read_text(encoding="utf-8"))
    completion = D01_COMPLETION.read_text(encoding="utf-8")
    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-D-01-completion-as-built.md" in epic["references"]
    assert "**IMPLEMENTING**" in epic10
    assert "| AS_BUILT | no |" in epic10
    assert "| FINAL | no |" in epic10
    assert "**IMPLEMENTING**" in epic12
    assert "| AS_BUILT | no |" in epic12
    assert "| FINAL | no |" in epic12
    assert policy["replay"]["controlled_result_reconstruction"]["status"] == "PASS_CONTROLLED_CI"
    assert policy["replay"]["controlled_result_reconstruction"]["execution_replayed"] is False
    assert policy["replay"]["controlled_result_reconstruction"]["authorization_replayed"] is False
    assert policy["runtime_status"]["encryption_at_rest"] == "NOT_RUN"
    assert policy["runtime_status"]["immutable_store"] == "NOT_RUN"
    assert policy["runtime_status"]["retention_enforcement"] == "NOT_RUN"
    assert policy["runtime_status"]["production_replay"] == "NOT_RUN"
    assert policy["runtime_status"]["production_redaction"] == "NOT_RUN"
    assert policy["runtime_status"]["customer_export"] == "NOT_RUN"
    assert policy["runtime_evidence"]["object_storage"] == "NOT_RUN"
    assert policy["runtime_evidence"]["worm_storage"] == "NOT_RUN"
    assert policy["runtime_evidence"]["deployed_runtime"] == "NOT_RUN"
    assert "SVP2-D-01`: **candidate for `completed`**" in completion
    assert "EPIC-10`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "EPIC-12`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "WORM/object storage: **`NOT_IMPLEMENTED` / `NOT_RUN`**" in completion
    assert "retention enforcement: **`NOT_IMPLEMENTED` / `NOT_RUN`**" in completion
    assert "production replay/redaction: **`NOT_RUN`**" in completion
    assert "DOD-10" in completion


def test_e01_delivery_completion_does_not_claim_graph_or_sync_finality() -> None:
    epic = _epics()["SVP2-E-01"]
    epic36 = EPIC_36.read_text(encoding="utf-8")
    policy = yaml.safe_load(KNOWLEDGE_SOURCE_POLICY.read_text(encoding="utf-8"))
    completion = E01_COMPLETION.read_text(encoding="utf-8")
    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-E-01-completion-as-built.md" in epic["references"]
    assert "**IMPLEMENTING**" in epic36
    assert "| AS_BUILT | no |" in epic36
    assert "| FINAL | no |" in epic36
    local = policy["controlled_local_integrity"]
    assert local["status"] == "PASS_CONTROLLED_CI"
    assert local["raw_create_only"] == "PASS_CONTROLLED_CI"
    assert local["raw_reopen_integrity"] == "PASS_CONTROLLED_CI"
    assert local["record_metadata_integrity"] == "PASS_CONTROLLED_CI"
    assert local["relation_provenance_gate"] == "PASS_CONTROLLED_CI"
    assert local["unresolved_conflict_persistence"] == "PASS_CONTROLLED_CI"
    assert local["explicit_resolution_without_historical_rewrite"] == "PASS_CONTROLLED_CI"
    assert local["execution_authority"] == "NONE"
    assert local["worm_or_admin_tamper_resistance"] == "NOT_CLAIMED"
    assert policy["conflicts"]["persist_all"] is True
    assert policy["conflicts"]["silent_resolution_allowed"] is False
    assert policy["precedence"]["mode"] == "explicit_policy_only"
    assert policy["precedence"]["default_winner"] == "none"
    assert policy["runtime_status"] == {
        "external_sync": "NOT_RUN",
        "taxii_sync": "NOT_RUN",
        "nvd_sync": "NOT_RUN",
        "kev_sync": "NOT_RUN",
        "epss_sync": "NOT_RUN",
        "graph_store": "NOT_IMPLEMENTED",
        "production_persistence": "NOT_RUN",
    }
    assert "SVP2-E-01`: **candidate for `completed`**" in completion
    assert "EPIC-36`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "external sync: **`NOT_RUN`**" in completion
    assert "production graph store: **`NOT_IMPLEMENTED`**" in completion
    assert "execution authority from knowledge: **`NONE`**" in completion
    assert "DOD-10" in completion
