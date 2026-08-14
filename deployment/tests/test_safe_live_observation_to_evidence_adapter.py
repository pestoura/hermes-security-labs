"""Repository-only tests for the SAFE live-observation -> EvidenceInput adapter (CHG-HSL-054).

The adapter is fail-closed: it only elevates an explicit ALLOWLIST of gates to PASS
(GATEWAY_ADMISSION_REOBSERVATION, BRIDGE_REVISION_REOBSERVATION) and only when the
exact observed evidence supports them. It never fabricates PASS for any other gate,
never rewrites the candidate commit, never mutates any artifact, and the resulting
package always stays HOLD with promotion_allowed=False.

These tests prove:
- tampered / ambiguous / stale / duplicate / missing observation evidence fail closed;
- anti-fabrication: HOST_IDENTITY_SOCKET_TRUST, USER_NAMESPACE_MAPPING, signer,
  receipt, peer-negative and every POST_EFFECT gate never become PASS;
- candidate commit provenance semantics (an ancestor of main is bound verbatim, never
  auto-repinned to HEAD);
- profile-aware omission/tombstone for LAB_L1 production WORM/tenant evidence;
- HOLD invariants and the ephemeral preview CLI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "safe_live_observation_to_evidence_adapter.py"
)
VERIFIER_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_live_promotion_evidence.py"
)
ASSEMBLER_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "offline_evidence_package_assembler.py"
)
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load("safe_obs_adapter_chg054", MODULE_PATH)
live = _load("safe_obs_adapter_verifier_chg054", VERIFIER_PATH)
asm = _load("safe_obs_adapter_assembler_chg054", ASSEMBLER_PATH)


# ---------------------------------------------------------------------------
# Helpers: build a disposable repo tree with synthetic SAFE observation artifacts
# ---------------------------------------------------------------------------


def _write_repo(tmp: Path, *, ledger: str | None = None, evidence: str | None = None) -> Path:
    (tmp / "docs" / "roadmap").mkdir(parents=True)
    (tmp / "deployment" / "runtime-promotion" / "evidence").mkdir(parents=True)
    (tmp / "validation").mkdir(parents=True)
    # Minimal campaign the adapter/assembler load: candidate commit = a63ef01 (ancestor).
    (tmp / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml").write_text(
        CAMPAIGN_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    if ledger is not None:
        (tmp / "docs" / "roadmap" / "safe-live-readonly-observation-test.md").write_text(
            ledger, encoding="utf-8"
        )
    if evidence is not None:
        (tmp / "deployment" / "runtime-promotion" / "evidence" / "live-observation-test.yaml").write_text(
            evidence, encoding="utf-8"
        )
    return tmp


_LEDGER_GOOD = """# Safe live read-only reobservation

Execution Gateway HOLD boundary | active; PID identity `4100`
Runner | active; PID identity `4101`
Dispatch socket | LISTEN; owner `4101:4110`; mode `0660`
Runner authorization trust store | `OBSERVED_ABSENT` (`/etc/hexor/runner/authorization-trust-store.json` not present)
uid_map / gid_map | observed `0 0 4294967295`
Namespace relationship | **NOT re-attested** -- ns/user dereference denied; no namespace relationship was derived or claimed

## RTA-003 Bridge SHA divergence -- resolved

- **Current live Hermes MCP Bridge revision (current live observation):** `3717bd5469b061a44294b27e1a7510d477d3752b` (Bridge 1.0.0).
- `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9 is retained ONLY as historical candidate/evidence` and must never be promoted to current.

## Explicitly retained NOT_RUN

- signer / provider observation: `NOT_RUN`
- peer-negative (unauthorized-peer) test: `NOT_RUN`
- first authorized effect + reset evidence: `NOT_RUN`
"""

_LEDGER_AMBIGUOUS_TWO_CURRENT = """# Ambiguous: two current Bridge SHAs

Execution Gateway HOLD boundary | active; PID identity `4100`
Runner authorization trust store | `OBSERVED_ABSENT`

- **Current live Hermes MCP Bridge revision (current live observation):** `1111111111111111111111111111111111111111`
- **Current live Hermes MCP Bridge revision (current live observation):** `2222222222222222222222222222222222222222`
"""

_LEDGER_AMBIGUOUS_CURRENT_IS_HISTORICAL = """# Ambiguous: current SHA is also marked historical-only

Execution Gateway HOLD boundary | active; PID identity `4100`
Runner authorization trust store | `OBSERVED_ABSENT`

- **Current live Hermes MCP Bridge revision (current live observation):** `9999999999999999999999999999999999999999`
- `9999999999999999999999999999999999999999 is retained ONLY as historical candidate/evidence`
"""

_LEDGER_STALE = """# Stale: no current Bridge SHA, trust store absent only

Execution Gateway HOLD boundary | active; PID identity `4100`
Runner authorization trust store | `OBSERVED_ABSENT`
"""

_STRUCTURED_GOOD = """schema_version: "1.0"
evidence_id: EVD-TEST
host_identity_socket_observation:
  observed:
    trust_store:
      path: /etc/hexor/runner/authorization-trust-store.json
      present: false
remaining_live_requirements:
  - RUNNER_AUTHORIZATION_TRUST_STORE_ABSENT
  - PRODUCTION_WORM_BACKEND_NOT_OBSERVED
  - BACKEND_TENANT_ISOLATION_NOT_OBSERVED
"""

_STRUCTURED_CONFLICTING_BRIDGE = """schema_version: "1.0"
evidence_id: EVD-TEST
host_identity_socket_observation:
  observed:
    trust_store:
      path: /etc/hexor/runner/authorization-trust-store.json
      present: false
"""


def _inputs_for(tmp: Path, *, profile: str = "LAB_L1") -> tuple[Any, Any]:
    return adapter.convert_observations_to_evidence_inputs(
        repo_root=tmp, phase="PRE_PROMOTION", profile=profile
    )


def _passing(inp: tuple[Any, Any]) -> set[str]:
    return {i.gate_id for i in inp[0]}


# ---------------------------------------------------------------------------
# Deterministic happy path against the real repo artifacts
# ---------------------------------------------------------------------------


def test_real_repo_artifact_maps_only_allowlisted_gates() -> None:
    inputs, facts = adapter.convert_observations_to_evidence_inputs(
        repo_root=ROOT, phase="PRE_PROMOTION", profile="LAB_L1"
    )
    passing = _passing((inputs, facts))
    # Allowlist gates map PASS; the other sources are OBSERVED_ABSENT tombstones.
    assert "GATEWAY_ADMISSION_REOBSERVATION" in passing
    assert "BRIDGE_REVISION_REOBSERVATION" in passing
    assert "HOST_IDENTITY_SOCKET_TRUST" not in passing
    assert "USER_NAMESPACE_MAPPING" not in passing
    assert "SIGNER_PROVIDER_ATTESTATION" not in passing
    assert "RECEIPT_DELIVERY" not in passing
    assert "UNAUTHORIZED_PEER_NEGATIVE" not in passing


def test_real_repo_facts_parsed() -> None:
    _, facts = adapter.convert_observations_to_evidence_inputs(
        repo_root=ROOT, phase="PRE_PROMOTION", profile="LAB_L1"
    )
    assert facts.gateway_boundary_active is True
    assert facts.gateway_pid == 4100
    assert facts.bridge_revision_current == "3717bd5469b061a44294b27e1a7510d477d3752b"
    assert facts.trust_store_absent is True
    assert facts.namespace_re_attested is False
    assert "safe-live-readonly-observation-ec368a4.md" in facts.sources
    assert "live-observation-CHG-HSL-038.yaml" in facts.sources


# ---------------------------------------------------------------------------
# Anti-fabrication: never PASS outside the allowlist / never PASS on absent trust
# ---------------------------------------------------------------------------


def test_host_identity_socket_trust_never_pass_while_trust_absent(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    passing = _passing(_inputs_for(repo))
    assert "HOST_IDENTITY_SOCKET_TRUST" not in passing


def test_user_namespace_mapping_never_pass_without_re_attestation(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    passing = _passing(_inputs_for(repo))
    assert "USER_NAMESPACE_MAPPING" not in passing


def test_signer_receipt_peer_negative_never_pass(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    passing = _passing(_inputs_for(repo))
    for g in (
        "SIGNER_PROVIDER_ATTESTATION",
        "RECEIPT_DELIVERY",
        "UNAUTHORIZED_PEER_NEGATIVE",
    ):
        assert g not in passing


def test_post_effect_gates_never_supplied(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    inputs, _ = _inputs_for(repo, profile="PROD")
    # None of the POST_EFFECT effect/reset gates may ever be produced.
    for g in (
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    ):
        assert g not in {i.gate_id for i in inputs}


def test_anti_fabrication_guard_in_source() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "HOST_IDENTITY_SOCKET_TRUST" in source  # explicit exclusion
    assert "ALLOWED_PASS_GATES" in source
    assert "ANTI_FABRICATION" in source


# ---------------------------------------------------------------------------
# Tampered / ambiguous / stale / duplicate / missing evidence
# ---------------------------------------------------------------------------


def test_tampered_markdown_two_current_bridge_is_not_pass(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_AMBIGUOUS_TWO_CURRENT)
    passing = _passing(_inputs_for(repo))
    assert "BRIDGE_REVISION_REOBSERVATION" not in passing
    # Gateway still maps because it is unambiguous.
    assert "GATEWAY_ADMISSION_REOBSERVATION" in passing


def test_tampered_current_equals_historical_is_not_pass(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_AMBIGUOUS_CURRENT_IS_HISTORICAL)
    passing = _passing(_inputs_for(repo))
    assert "BRIDGE_REVISION_REOBSERVATION" not in passing


def test_stale_ledger_missing_bridge_is_not_pass(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_STALE)
    passing = _passing(_inputs_for(repo))
    assert "BRIDGE_REVISION_REOBSERVATION" not in passing
    assert "GATEWAY_ADMISSION_REOBSERVATION" in passing


def test_duplicate_conflicting_sources_merge_fail_closed(tmp_path: Path) -> None:
    # Two artifacts disagree on the current bridge SHA -> merged to None (fail-closed).
    (tmp_path / "docs" / "roadmap").mkdir(parents=True)
    (tmp_path / "deployment" / "runtime-promotion" / "evidence").mkdir(parents=True)
    (tmp_path / "validation").mkdir(parents=True)
    (tmp_path / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml").write_text(
        CAMPAIGN_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    l1 = _LEDGER_GOOD.replace(
        "3717bd5469b061a44294b27e1a7510d477d3752b",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    l2 = _LEDGER_GOOD.replace(
        "3717bd5469b061a44294b27e1a7510d477d3752b",
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    (tmp_path / "docs" / "roadmap" / "safe-live-readonly-observation-a.md").write_text(l1, encoding="utf-8")
    (tmp_path / "docs" / "roadmap" / "safe-live-readonly-observation-b.md").write_text(l2, encoding="utf-8")
    passing = _passing(_inputs_for(tmp_path))
    assert "BRIDGE_REVISION_REOBSERVATION" not in passing


def test_missing_evidence_yields_empty_inputs(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path)  # no ledger, no evidence
    inputs, facts = _inputs_for(repo, profile="PROD")  # PROD: no tombstones, nothing supplied
    assert tuple(inputs) == ()
    assert facts.sources == ()


def test_tampered_produced_package_stays_hold(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    inputs, _ = _inputs_for(repo)
    # Force a fabricated PASS on a forbidden gate by tampering the assembled package.
    assembled = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="tamper-pkg",
        evidence=inputs,
        evidence_chain_document=None,
    )
    tampered = json.loads(json.dumps(assembled.package))
    for gate in tampered["gates"]:
        if gate["gate_id"] == "HOST_IDENTITY_SOCKET_TRUST":
            gate["result"] = "PASS"
            gate["observed_at"] = "2026-08-14T00:00:00Z"
            gate["evidence_ref"] = "evidence://x/y.json"
            gate["evidence_sha256"] = "0" * 64
    result = live.verify_live_evidence_package(tampered, live.load_campaign())
    # Fabricated HOST_IDENTITY_SOCKET_TRUST PASS cannot manufacture promotion.
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.package_complete is False


# ---------------------------------------------------------------------------
# Candidate commit provenance (ancestor of main, never auto-repinned)
# ---------------------------------------------------------------------------


def test_candidate_commit_bound_verbatim_not_repinned_to_head() -> None:
    # a63ef01 is an ancestor of origin/main HEAD (62a690d) and is the campaign commit.
    out = tmp_path_ctx() / "preview.json"
    preview = adapter.generate_ephemeral_preview(
        repo_root=ROOT,
        out_path=out,
        candidate_commit="a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5",
    )
    # The adapter binds exactly the supplied ancestor SHA; it never substitutes 62a690d.
    assert preview["candidate_commit_bound"] == "a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5"
    assert preview["candidate_commit_bound"] != "62a690de9fa925be9ab0686c53cfe1e620cc6f40"


def test_candidate_commit_none_defaults_to_campaign_commit() -> None:
    out = tmp_path_ctx() / "preview2.json"
    preview = adapter.generate_ephemeral_preview(repo_root=ROOT, out_path=out)
    assert preview["candidate_commit_bound"] == "a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5"


def test_adapter_source_does_not_rewrite_candidate_commit() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    # The adapter must not reach for git or rewrite the candidate commit.
    for forbidden in ("origin/main", "git rev-parse"):
        assert forbidden not in source
    # The exact supplied commit is bound verbatim (no auto-repin mechanism present).
    assert "candidate_commit" in source
    assert "auto_repin_commit" not in source


# ---------------------------------------------------------------------------
# Profile-aware omission / tombstone (LAB_L1 vs PROD)
# ---------------------------------------------------------------------------


def test_lab_l1_omits_backend_tenant_as_observed_absent(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD, evidence=_STRUCTURED_GOOD)
    inputs, _ = _inputs_for(repo, profile="LAB_L1")
    passed = {i.gate_id: i for i in inputs}
    assert "EVIDENCE_BACKEND_CONTROLS" in passed
    assert passed["EVIDENCE_BACKEND_CONTROLS"].observed_absent is True
    assert "EVIDENCE_TENANT_ISOLATION" in passed
    assert passed["EVIDENCE_TENANT_ISOLATION"].observed_absent is True


def test_prod_backend_tenant_not_observed_absent(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD, evidence=_STRUCTURED_GOOD)
    inputs, _ = _inputs_for(repo, profile="PROD")
    passed = {i.gate_id: i for i in inputs}
    # Under PROD the production backend / tenant isolation are simply NOT_RUN, not
    # emitted as OBSERVED_ABSENT tombstones, and never PASS.
    assert "EVIDENCE_BACKEND_CONTROLS" not in passed
    assert "EVIDENCE_TENANT_ISOLATION" not in passed


def test_profile_aware_omission_preserved_through_verifier(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD, evidence=_STRUCTURED_GOOD)
    inputs, _ = _inputs_for(repo, profile="LAB_L1")
    assembled = asm.assemble_hold_package(
        phase="PRE_PROMOTION", package_id="profile-pkg", evidence=inputs
    )
    absent = assembled.observed_absent_gate_ids
    assert "EVIDENCE_BACKEND_CONTROLS" in absent
    assert "EVIDENCE_TENANT_ISOLATION" in absent
    result = live.verify_live_evidence_package(assembled.package, live.load_campaign())
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"


# ---------------------------------------------------------------------------
# HOLD invariants + determinism
# ---------------------------------------------------------------------------


def test_ephemeral_preview_stays_hold() -> None:
    out = tmp_path_ctx() / "preview3.json"
    preview = adapter.generate_ephemeral_preview(
        repo_root=ROOT, out_path=out, candidate_commit="a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5"
    )
    assert preview["verifier"]["promotion_allowed"] is False
    assert preview["verifier"]["recommendation"] == "HOLD"
    assert preview["verifier"]["package_complete"] is False
    assert "HOST_IDENTITY_SOCKET_TRUST" not in preview["passing_gates"]


def test_preview_is_ephemeral_outside_repo(tmp_path: Path) -> None:
    inside = ROOT / "preview-inside-repo.json"
    with pytest.raises(adapter.AdapterError):
        adapter.generate_ephemeral_preview(repo_root=ROOT, out_path=inside)
    assert not inside.exists()


def test_adapter_is_deterministic(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD, evidence=_STRUCTURED_GOOD)
    a = adapter.convert_observations_to_evidence_inputs(repo_root=repo, profile="LAB_L1")
    b = adapter.convert_observations_to_evidence_inputs(repo_root=repo, profile="LAB_L1")
    assert [i.gate_id for i in a[0]] == [i.gate_id for i in b[0]]
    assert a[1].sources == b[1].sources


def test_campaign_blocked_hold_unchanged() -> None:
    campaign = CAMPAIGN_PATH.read_text(encoding="utf-8")
    assert "state: BLOCKED" in campaign
    assert "promotionRecommendation: HOLD" in campaign
    # The adapter never mutates the campaign file.
    assert "validation/VAL" not in MODULE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AST: no collection / mutation / target execution / promote / trust binding
# ---------------------------------------------------------------------------


def test_adapter_source_has_no_collection_mutation_or_target_execution_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "requests",
        "http.client",
        "subprocess",
        "docker",
        "boto3",
        "azure.storage",
        "google.cloud",
        "os.chmod",
        "os.chown",
        ".sign(",
        "systemd",
        "promote(",
        "promotion_allowed=True",
        'recommendation="PROMOTE"',
        "bind_trust",
        "trust_store_json",
    ):
        assert forbidden not in source
    # The adapter must not reach for git, a network socket import, or rewrite the
    # candidate commit. 'socket' as a Python module import / 'import socket' and the
    # literal 'origin/main' string are both disallowed (the docstring discusses the
    # AF_UNIX dispatch *socket* only in prose, never the module).
    assert "import socket" not in source
    assert "origin/main" not in source
    assert "HOLD" in source
    assert "NOT_RUN" in source
    assert "ALLOWED_PASS_GATES" in source


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_inputs_lists_allowlist_gates(tmp_path: Path, capsys) -> None:
    repo = _write_repo(tmp_path, ledger=_LEDGER_GOOD)
    code = adapter.main(["inputs", "--repo", str(repo)])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "GATEWAY_ADMISSION_REOBSERVATION" in payload["passing_gates"]
    assert "BRIDGE_REVISION_REOBSERVATION" in payload["passing_gates"]
    assert payload["trust_store_absent"] is True
    assert payload["namespace_re_attested"] is False


def tmp_path_ctx() -> Path:
    """Provide an outside-repo path for ephemeral preview output."""
    import tempfile

    d = Path(tempfile.gettempdir()) / "hsl054-preview"
    d.mkdir(parents=True, exist_ok=True)
    return d
