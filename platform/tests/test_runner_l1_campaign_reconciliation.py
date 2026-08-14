from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# Canonical observation identifier contract (shared with the change-record guard):
# OBS- followed by one or more uppercase alphanumeric segments separated by single
# hyphens. Free-form ids (lowercase, underscores, spaces, stray punctuation) are
# rejected fail-closed.
CANONICAL_OBSERVATION_ID = re.compile(r"^OBS-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
STATUS_PATH = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EPIC_PATH = ROOT / "docs" / "roadmap" / "epics" / "EPIC-10-evidence-plane.md"
BASELINE = "c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c"


def _campaign() -> dict:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_campaign_reconciles_repository_candidate_without_promoting_live_state() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    assert campaign["candidate"]["commit"] == BASELINE

    observations = {item["id"]: item for item in campaign["observations"]}
    assert observations["OBS-RUNNER-REPO-CHAIN"]["result"] == "PASS"
    assert observations["OBS-RUNNER-REPO-CHAIN"]["status"] == "RESOLVED"

    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["required"] is True
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"


def test_campaign_records_current_repo_capabilities_as_non_live_evidence() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    repo_evidence = observations["OBS-RUNNER-REPO-CHAIN"]["evidence"]
    for pr in (
        "335",
        "336",
        "337",
        "338",
        "340",
        "341",
        "342",
        "343",
        "345",
        "346",
        "348",
        "349",
        "350",
        "351",
        "352",
    ):
        assert pr in repo_evidence

    tb1 = observations["OBS-TB1-LIVE-DELIVERY"]
    assert "signer-observation verification" in tb1["summary"]
    assert "signer-provider-observation:NOT_RUN" in tb1["evidence"]
    assert "signer-source-evidence:NOT_RUN" in tb1["evidence"]

    policy = observations["OBS-RUNNER-POLICY-PROMOTION"]
    assert "tenant-isolation verification" in policy["summary"]
    assert "phased live-evidence package verification" in policy["summary"]
    # The user-namespace observation collector has now been run live and PASSED
    # for the two reviewed PIDs (CHG-HSL-038). That is an observation class only:
    # the Runner authorization trust store is still ABSENT, so promotion stays
    # blocked and the observation remains BLOCKED/OPEN.
    assert "userns:PASS" in policy["evidence"]
    assert "trust-store:ABSENT" in policy["evidence"]
    assert "live-observation-CHG-HSL-038.yaml" in policy["evidence"]
    assert "production-backend:NOT_IMPLEMENTED/NOT_RUN" in policy["evidence"]
    assert "tenant-isolation:NOT_RUN" in policy["evidence"]
    assert "live-evidence-package-verifier:GREEN-REPO" in policy["evidence"]
    assert "pre-promotion-package:NOT_RUN" in policy["evidence"]
    assert "post-effect-package:NOT_RUN" in policy["evidence"]
    assert "DISABLED/NOT_RUN" in policy["summary"]

    evidence = observations["OBS-EVIDENCE-CUSTODY"]
    assert "phased live-evidence package verifiers are also GREEN-REPO" in evidence["summary"]
    assert "durable-backend-verifier:GREEN-REPO" in evidence["evidence"]
    assert "tenant-isolation-verifier:GREEN-REPO" in evidence["evidence"]
    assert "live-evidence-package-verifier:GREEN-REPO" in evidence["evidence"]
    assert "production-WORM-backend:NOT_IMPLEMENTED/NOT_RUN" in evidence["evidence"]
    assert "backend-tenant-config:NOT_RUN" in evidence["evidence"]
    assert "cross-tenant-negatives:NOT_RUN" in evidence["evidence"]
    assert "pre-promotion-package:NOT_RUN" in evidence["evidence"]
    assert "post-effect-package:NOT_RUN" in evidence["evidence"]


def test_walking_skeleton_status_uses_same_baseline_and_hold_state() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert f"**Current Labs baseline:** `{BASELINE}`" in text
    assert "GREEN-REPO is not live acceptance" in text
    assert "Evidence Plane backend tenant-isolation verifier" in text
    assert "Tenant-isolation promotion reconciliation" in text
    assert "Phased live-promotion evidence package" in text
    assert "Live-package promotion reconciliation" in text
    assert "real tenant config/evidence and cross-tenant negatives `NOT_RUN`" in text
    assert "production backend `NOT_IMPLEMENTED / NOT_RUN`" in text
    assert "PRE_PROMOTION and POST_EFFECT packages `NOT_RUN`" in text
    assert "promotion_allowed=false" in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR" in text


def test_epic10_records_tenant_verifier_without_claiming_live_isolation() -> None:
    text = EPIC_PATH.read_text(encoding="utf-8")
    assert "Document version | 1.5.0" in text
    assert "backend tenant-isolation attestation verifier: `GREEN_REPO`" in text
    assert "production backend selection/deployment: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "production tenant configuration: `NOT_RUN`" in text
    assert "cross-tenant list/read/write negative acceptance: `NOT_RUN`" in text
    assert "A GREEN tenant-isolation verifier does not mean tenant isolation has run live" in text
    assert "Evidence Record v2 is not modified" in text
    assert "`AS_BUILT` for the complete concept remains false" in text
    assert "`FINAL` remains false" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_unknown_webgoat_rerun_is_not_promoted_to_pass_or_fail() -> None:
    campaign = _campaign()
    observation = next(
        item for item in campaign["observations"] if item["id"] == "OBS-LIVE-EFFECT-RESET"
    )
    assert "result=UNKNOWN" in observation["evidence"]
    assert "live-runner-effect:NOT_RUN" in observation["evidence"]
    assert "post-effect-package:NOT_RUN" in observation["evidence"]


def test_chg_hsl_047_records_merged_green_repo_capability_tokens_without_resolving_live_state() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    repo_chain = observations["OBS-RUNNER-REPO-CHAIN"]
    assert repo_chain["result"] == "PASS"
    assert repo_chain["status"] == "RESOLVED"

    policy = observations["OBS-RUNNER-POLICY-PROMOTION"]
    assert "DISABLED/NOT_RUN" in policy["evidence"]

    evidence = observations["OBS-EVIDENCE-CUSTODY"]
    assert "hash-chain-seal:GREEN-REPO(CHG-042)" in evidence["evidence"]
    assert "audit-sink:GREEN-REPO(CHG-043)" in evidence["evidence"]
    assert "profile-aware-pre-post:GREEN-REPO(CHG-044)" in evidence["evidence"]
    assert "package-composition:GREEN-REPO(CHG-046)" in evidence["evidence"]
    assert "peer-identity-audit:GREEN-REPO(CHG-045)" in evidence["evidence"]
    assert "HASH_CHAIN_SEAL:NOT_RUN" in evidence["evidence"]
    assert "CHG-HSL-047 reconciles" in evidence["summary"]


def test_chg_hsl_050_execution_gateway_holds_are_implemented_green_repo_but_unpromoted() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    # Issues #359 (runtime HOLD) and #361 (deployment controller) are part of
    # the repository chain as fail-closed, NOT-promoted capabilities. They must
    # be recorded as IMPLEMENTED/GREEN-REPO and explicitly UNPROMOTED.
    repo_chain = observations["OBS-RUNNER-REPO-CHAIN"]
    assert "execution-gateway-hold:IMPLEMENTED(CHG-036;issue#359:GREEN-REPO)" in repo_chain["evidence"]
    assert "execution-gateway-deployment:IMPLEMENTED(CHG-037;issue#361:GREEN-REPO)" in repo_chain["evidence"]
    assert "execution-gateway-boundary:UNPROMOTED(promotion_allowed=false;HOLD)" in repo_chain["evidence"]

    # The live observation is still unpromoted: the campaign stays BLOCKED/HOLD
    # and the #359/#361 observations remain OPEN (not closed by this record).
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    assert repo_chain["result"] == "PASS"
    assert repo_chain["status"] == "RESOLVED"


def test_chg_hsl_050_records_merged_green_repo_capability_tokens_042_047() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    # CHG-042..047 merged LAB_L1 capabilities reconciled as GREEN-REPO (no live
    # promotion). Every token must be present in OBS-EVIDENCE-CUSTODY evidence.
    evidence = observations["OBS-EVIDENCE-CUSTODY"]["evidence"]
    tokens = (
        "hash-chain-seal:GREEN-REPO(CHG-042)",
        "audit-sink:GREEN-REPO(CHG-043)",
        "profile-aware-pre-post:GREEN-REPO(CHG-044)",
        "peer-identity-audit:GREEN-REPO(CHG-045)",
        "package-composition:GREEN-REPO(CHG-046)",
    )
    for token in tokens:
        assert token in evidence
    # CHG-047 is the record that performed the reconciliation; it is cited too.
    assert "CHG-HSL-047 reconciles" in observations["OBS-EVIDENCE-CUSTODY"]["summary"]
    # HASH_CHAIN_SEAL stays NOT_RUN for live evidence (GREEN-REPO != live seal).
    assert "HASH_CHAIN_SEAL:NOT_RUN" in evidence


def test_chg_hsl_050_assurance_profile_invariants_stay_locked_in() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    # The live promotion observations must NOT be flipped to PASS/RESOLVED by the
    # merged repo capabilities: they remain required/BLOCKED/OPEN.
    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["required"] is True
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"


def test_chg_hsl_047_preserves_blocked_hold_invariants() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"

    observations = {item["id"]: item for item in campaign["observations"]}
    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"


def test_chg_hsl_050_preserves_blocked_hold_invariants() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"

    observations = {item["id"]: item for item in campaign["observations"]}
    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"


def test_val_observation_ids_are_schema_valid() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}
    invalid = [
        observation_id
        for observation_id in observations
        if not CANONICAL_OBSERVATION_ID.match(str(observation_id))
    ]
    assert not invalid, f"campaign defines non-canonical observation ids: {invalid}"


def test_val_observation_change_records_reference_defined_change_records() -> None:
    campaign = _campaign()
    change_records = {
        document["id"]
        for document in (
            yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "changes").glob("CHG-HSL-*.yaml"))
        )
        if isinstance(document, dict) and document.get("id")
    }
    observations = {item["id"]: item for item in campaign["observations"]}
    dangling = [
        (observation_id, observations[observation_id].get("changeRecord"))
        for observation_id, observation in observations.items()
        if observation.get("changeRecord")
        and observation["changeRecord"] not in change_records
    ]
    assert not dangling, f"observations reference undefined change records: {dangling}"


def test_chg_hsl_048_reserves_hardening_record_without_resolving_live_state() -> None:
    # CHG-HSL-048 hardens the observation/change consistency contract. The campaign
    # itself must remain BLOCKED/HOLD and no live observation may be resolved by it.
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"

    observations = {item["id"]: item for item in campaign["observations"]}
    assert all(
        observations[observation_id]["result"] == "BLOCKED"
        for observation_id in (
            "OBS-TB1-LIVE-DELIVERY",
            "OBS-RUNNER-POLICY-PROMOTION",
            "OBS-EVIDENCE-CUSTODY",
            "OBS-LIVE-EFFECT-RESET",
        )
    )


# --- CHG-HSL-052: repository-only walking-skeleton reconciliation -----------------
#
# These guards keep the reconciliation honest: the walking-skeleton status doc and the
# campaign must track the authoritative Git HEAD, must NOT treat a commit SHA as a
# runtime authority, must preserve UNKNOWN/BLOCKED/HOLD fail-safe semantics, and must
# keep Git + the campaign as the only sources of truth. No runtime/live mutation.


def test_chg_hsl_052_status_and_campaign_track_authoritative_head() -> None:
    # Both the status doc and the campaign candidate must reflect the exact
    # authoritative origin/main at reconciliation time (CHG-042..050, PR #378).
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c" in text
    # The stale baseline must no longer be declared as the current baseline (the
    # historical #352 merge SHA may still appear in the checkpoint table).
    assert (
        "**Current Labs baseline:** `6a77921ec2079aa6689d11e2d7118f948ccb3a60`"
        not in text
    )
    assert (
        "**Current Labs baseline:** `c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c`" in text
    )

    campaign = _campaign()
    assert campaign["candidate"]["commit"] == "c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c"


def test_chg_hsl_052_commit_sha_is_provenance_not_runtime_authority() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    # The doc must explicitly forbid treating the SHA as a runtime authority.
    assert "commit SHA is reconciliation provenance, not a runtime authority" in text
    assert "not read by any runtime, gate, policy or promotion path" in text
    # Git + the campaign remain the only sources of truth.
    assert "Git and `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` remain the only sources of truth" in text


def test_chg_hsl_052_lifecycle_matrix_is_present_and_explicit() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "## Lifecycle matrix (repository vs live vs deferred)" in text
    # Three-state separation must be explicit.
    assert "GREEN-REPO" in text
    assert "NOT_RUN / HOLD" in text
    assert "Deferred signer / Vault dependency" in text
    # The forbidden promotion rule must be stated.
    assert "GREEN-REPO` row never implies the live row is `PASS`" in text
    # UNKNOWN fail-safe must be preserved in the matrix contract.
    assert "UNKNOWN` is fail-safe" in text
    # Deferred signer/Vault dependency must be named for the key live blockers.
    assert "trust-store: ABSENT" in text
    assert "production-backend: NOT_IMPLEMENTED / NOT_RUN" in text
    assert "tenant-isolation: NOT_RUN" in text


def test_chg_hsl_052_git_and_campaign_remain_only_sources_of_truth() -> None:
    # The reconciliation re-pins to Git HEAD and the campaign; it does not introduce
    # any new source-of-truth authority (no SHA-derived runtime claim).
    campaign = _campaign()
    # Campaign stays the governed source for promotion state.
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    assert campaign["candidate"]["commit"] == BASELINE
    # The status doc still refuses to equate GREEN-REPO with live acceptance.
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "GREEN-REPO is not live acceptance" in text


def test_chg_hsl_052_preserves_unknown_fail_safe_and_blocked_hold() -> None:
    # Re-pinning the baseline must not resolve any live observation or flip BLOCKED/HOLD.
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"

    observations = {item["id"]: item for item in campaign["observations"]}
    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["required"] is True
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"

    # UNKNOWN stays fail-safe: the post-fix WebGoat rerun is still UNKNOWN, not PASS/FAIL.
    reset = observations["OBS-LIVE-EFFECT-RESET"]
    assert "result=UNKNOWN" in reset["evidence"]
    assert "live-runner-effect:NOT_RUN" in reset["evidence"]


def test_chg_hsl_052_reconciles_checkpoint_rows_without_promoting_live_state() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    # CHG-042..050 merge SHAs must appear in the engineering-checkpoint table.
    for sha in (
        "1236667779f0a7b55e7b2fcd394b57680e070eac",  # CHG-042 #369
        "47a3ea8c97f146cb5869540b6c9ec8e2d56a8e2a",  # CHG-043 #370
        "970b3a38d5b9a909a554e11c3e495d33cbc8d699",  # CHG-044 #371
        "59d212ee09ea5e746b873462ca4b32f9d1add2d9",  # CHG-046 #372
        "9bdc59409ea14ed238915ff6356b76fe91849add",  # CHG-045 #373/#374
        "d545ccbd4d4def5aeb8793d291adbc0313e69258",  # CHG-048 #376
        "567e143af332b96b37c0a2aaf6cb563a30cad93c",  # CHG-049 #377
        "c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c",  # CHG-050 #378 + CHG-HSL-052
    ):
        assert sha in text, f"missing checkpoint SHA {sha}"
