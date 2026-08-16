from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_OBSERVATION_ID = re.compile(r"^OBS-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
STATUS_PATH = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EPIC_PATH = ROOT / "docs" / "roadmap" / "epics" / "EPIC-10-evidence-plane.md"
CHG071_PATH = ROOT / "changes" / "CHG-HSL-071.yaml"
CHG072_PATH = ROOT / "changes" / "CHG-HSL-072.yaml"
CHG038_EVIDENCE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "evidence"
    / "live-observation-CHG-HSL-038.yaml"
)
CHG071_EVIDENCE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "evidence"
    / "live-custody-verification-CHG-HSL-071.yaml"
)
CHG072_EVIDENCE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "evidence"
    / "live-operator-observation-CHG-HSL-072.yaml"
)
BASELINE = "c716bd6512da3fa853ad8022863ecc8bac4e51a6"
STATUS_BASELINE = "8c654379afb2114e34d6e748bb558b3ad5b8fb4b"
CHG072_RECONCILIATION_BASE = "9448817e436ee096e0f839b6bb8b9bf9e06d8d6d"


def _campaign() -> dict:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _observations() -> dict[str, dict]:
    return {item["id"]: item for item in _campaign()["observations"]}


def test_campaign_candidate_and_promotion_invariants_stay_locked() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    assert campaign["candidate"]["commit"] == BASELINE
    assert campaign["candidate"]["artifactDigest"] is None

    observations = _observations()
    assert observations["OBS-RUNNER-REPO-CHAIN"]["result"] == "PASS"
    assert observations["OBS-RUNNER-REPO-CHAIN"]["status"] == "RESOLVED"

    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        observation = observations[observation_id]
        assert observation["required"] is True
        assert observation["result"] == "BLOCKED"
        assert observation["status"] == "OPEN"


def test_campaign_fields_fit_jds_002_limits() -> None:
    campaign = _campaign()
    assert len(campaign["objective"]) <= 500
    for observation in campaign["observations"]:
        assert len(observation["summary"]) <= 500, observation["id"]
        evidence = observation.get("evidence")
        if evidence is not None:
            assert len(evidence) <= 500, observation["id"]


def test_observation_ids_and_change_records_are_canonical() -> None:
    campaign = _campaign()
    change_records = {
        document["id"]
        for document in (
            yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "changes").glob("CHG-HSL-*.yaml"))
        )
        if isinstance(document, dict) and document.get("id")
    }

    for observation in campaign["observations"]:
        assert CANONICAL_OBSERVATION_ID.match(observation["id"]), observation["id"]
        change_record = observation.get("changeRecord")
        if change_record:
            assert change_record in change_records, (observation["id"], change_record)


def test_repository_chain_remains_green_repo_not_runtime_authority() -> None:
    repo_chain = _observations()["OBS-RUNNER-REPO-CHAIN"]
    evidence = repo_chain["evidence"]
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
        "417",
    ):
        assert pr in evidence
    assert "authorization-audit-custody:GREEN-REPO(CHG-HSL-079;ADR-0016;PR#417;post-merge-exact-sha=PASS)" in evidence
    assert "execution-gateway-hold:IMPLEMENTED(CHG-036;issue#359:GREEN-REPO)" in evidence
    assert "execution-gateway-deployment:IMPLEMENTED(CHG-037;issue#361:GREEN-REPO)" in evidence
    assert "execution-gateway-boundary:UNPROMOTED(promotion_allowed=false;HOLD)" in evidence


def test_tb1_live_delivery_remains_blocked_without_signer_trust_and_endpoint() -> None:
    tb1 = _observations()["OBS-TB1-LIVE-DELIVERY"]
    evidence = tb1["evidence"]
    assert tb1["result"] == "BLOCKED"
    assert tb1["status"] == "OPEN"
    assert "trust-store:ABSENT" in evidence
    assert "signer-provider:NOT_RUN" in evidence
    assert "signer-source:NOT_RUN" in evidence
    assert "receipt-delivery:DISABLED/NOT_RUN" in evidence
    assert "resolver:DISABLED/NOT_RUN" in evidence
    assert "auth-audit-custody:GREEN-REPO(CHG-HSL-079)" in evidence
    assert "auth-audit-custody-policy:DISABLED/NOT_RUN" in evidence
    assert "live-auth-audit:NOT_RUN" in evidence


def test_policy_observation_reconciles_current_userns_peer_and_audit_custody() -> None:
    policy = _observations()["OBS-RUNNER-POLICY-PROMOTION"]
    evidence = policy["evidence"]

    assert policy["changeRecord"] == "CHG-HSL-072"
    assert "userns:PASS(CHG-HSL-072)" in evidence
    assert "peer-negative:PASS(CHG-HSL-072)" in evidence
    assert "auth-audit-custody:GREEN-REPO(CHG-HSL-079;main=c716bd6512da3fa853ad8022863ecc8bac4e51a6)" in evidence
    assert "trust-store:ABSENT" in evidence
    assert "signer:NOT_OBSERVED" in evidence
    assert "auth-audit-custody-policy:DISABLED/NOT_RUN" in evidence
    assert "live-audit-custody:NOT_RUN" in evidence
    assert "pre:ASSEMBLED/HOLD/INCOMPLETE(CHG-HSL-071)" in evidence
    assert "post-effect:NOT_RUN" in evidence
    assert "policies:DISABLED/NOT_RUN" in evidence
    assert "ROOT_REQUIRED" not in evidence
    assert "peer-negative:NOT_PROVEN" not in evidence

    summary = policy["summary"]
    assert "CHG-HSL-072: userns PASS" in summary
    assert "unauthorized-peer HOLD refusal PASS" in summary
    assert "CHG-HSL-079: auth-audit custody GREEN-REPO" in summary
    assert "live composition NOT_RUN" in summary
    assert "Remaining LAB_L1 blockers" in summary
    assert policy["result"] == "BLOCKED"


def test_chg_hsl_079_and_080_reconcile_custody_without_promotion() -> None:
    custody = _observations()["OBS-EVIDENCE-CUSTODY"]
    evidence = custody["evidence"]

    assert custody["result"] == "BLOCKED"
    assert custody["status"] == "OPEN"
    assert custody["changeRecord"] == "CHG-HSL-080"
    assert "auth-audit-custody:GREEN-REPO(CHG-HSL-079;ADR-0016;PR#417;main=c716bd6512da3fa853ad8022863ecc8bac4e51a6)" in evidence
    assert "post-merge:PASS(all-4-workflows;exact-sha)" in evidence
    assert "custody-policy:DISABLED/NOT_RUN" in evidence
    assert "live-audit-custody:NOT_RUN" in evidence
    assert "hash-chain:VERIFIED(CHG-HSL-071)" in evidence
    assert "userns:PASS(CHG-HSL-072)" in evidence
    assert "peer-negative:PASS(CHG-HSL-072)" in evidence
    assert "pre:ASSEMBLED/HOLD/INCOMPLETE" in evidence
    assert "post-effect:NOT_RUN" in evidence

    summary = custody["summary"]
    assert "CHG-HSL-079/ADR-0016 closes repository auth-audit custody" in summary
    assert "content identity and ev_<id> custody binding remain distinct" in summary
    assert "GREEN-REPO only" in summary
    assert "custody policy DISABLED/NOT_RUN" in summary
    assert "live custody NOT_RUN" in summary
    assert "Campaign remains BLOCKED/HOLD" in summary
    assert "signer/trust, delivery, PRE, HITL, effect and POST_EFFECT remain open" in summary


def test_prod_only_controls_are_not_lab_l1_blockers_in_chg071_record() -> None:
    evidence = yaml.safe_load(CHG071_EVIDENCE_PATH.read_text(encoding="utf-8"))
    blockers = set(evidence["remaining_lab_l1_blockers"])
    prod_only = evidence["prod_only_deferred_readiness"]

    assert "EVIDENCE_BACKEND_CONTROLS" not in blockers
    assert "EVIDENCE_TENANT_ISOLATION" not in blockers
    assert prod_only["controls"] == [
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
    ]
    assert "not LAB_L1 blockers" in prod_only["note"]


def test_chg071_evidence_is_sanitized_and_incomplete_hold() -> None:
    evidence = yaml.safe_load(CHG071_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["change_record"] == "CHG-HSL-071"
    assert evidence["campaign"] == "VAL-HSL-RUNNER-L1-LIVE-PROMOTION"
    assert evidence["verdicts"]["package_phase"] == "PRE_PROMOTION"
    assert evidence["verdicts"]["package_status"] == "ASSEMBLED"
    assert evidence["verdicts"]["package_recommendation"] == "HOLD"
    assert evidence["verdicts"]["promotion_allowed"] is False
    assert evidence["verdicts"]["authorized_effect_claimed"] is False
    assert evidence["verdicts"]["read_only_package_validator"]["package_valid"] is True
    assert evidence["verdicts"]["read_only_package_validator"]["package_complete"] is False
    assert evidence["verdicts"]["hash_chain_seal"]["result"] == "PASS"
    assert evidence["verdicts"]["hash_chain_seal"]["seal_status"] == "SEAL_OK"
    assert evidence["verdicts"]["hash_chain_seal"]["integrity"] is True
    assert evidence["verdicts"]["hash_chain_seal"]["authenticity"] is False
    assert evidence["verdicts"]["hash_chain_seal"]["durability"] is False

    sanitization = evidence["sanitization"]
    assert sanitization["secrets_found"] is False
    assert sanitization["private_keys_found"] is False
    assert sanitization["tokens_found"] is False
    assert sanitization["passwords_found"] is False
    assert sanitization["cookies_found"] is False

    invariants = evidence["promotion_invariants"]
    assert invariants["promotion_allowed"] is False
    assert invariants["runtime_status"] == "NOT_RUN"
    assert invariants["execution_authority"] == "none"
    assert invariants["recommendation"] == "HOLD"
    assert invariants["state"] == "BLOCKED"


def test_chg071_change_record_is_repo_only_and_non_promoting() -> None:
    record = yaml.safe_load(CHG071_PATH.read_text(encoding="utf-8"))
    assert record["id"] == "CHG-HSL-071"
    assert record["classification"] == "DOC_ONLY"
    assert record["state"] == "ACCEPTED"
    assert record["source"]["campaign"] == "VAL-HSL-RUNNER-L1-LIVE-PROMOTION"
    assert record["source"]["observation"] == "OBS-EVIDENCE-CUSTODY"
    assert record["validation"]["targeted"] == "PASS"
    assert record["validation"]["regression"] == "PASS"
    assert record["validation"]["security"] == "PASS"
    assert record["validation"]["runtime"] == "NOT_APPLICABLE"
    assert record["promotion"]["commit"] is None
    assert record["promotion"]["artifactDigest"] is None


def test_chg072_evidence_is_current_sanitized_and_non_promoting() -> None:
    evidence = yaml.safe_load(CHG072_EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["change_record"] == "CHG-HSL-072"
    assert evidence["campaign"] == "VAL-HSL-RUNNER-L1-LIVE-PROMOTION"
    assert evidence["repository_sha"] == CHG072_RECONCILIATION_BASE
    assert evidence["source_artifacts"]["operator_evidence_sha256"] == (
        "bf7a2b498cd9a547852d594b8c2cc43bbefbe73ee4eddc5c7ca3b7ad5d11a2a8"
    )
    assert evidence["source_artifacts"]["descriptor_sha256"] == (
        "e10cdbe95e58f5ffde74c000bb660415eb945ae93e48be863397e7c3ba4257d5"
    )

    userns = evidence["user_namespace_mapping"]
    assert userns["result"] == "PASS"
    assert userns["re_attested"] is True
    assert userns["findings"] == []
    assert userns["gateway"]["pid"] == 3649254
    assert userns["gateway"]["process_start_time_ticks"] == 334245705
    assert userns["runner"]["pid"] == 409235
    assert userns["runner"]["process_start_time_ticks"] == 338949789
    assert userns["user_namespace_relationship"] == "same"

    peer = evidence["unauthorized_peer_negative"]
    assert peer["result"] == "PASS"
    assert peer["outcome"] == "HOLD_REFUSAL_OBSERVED"
    assert peer["canonical_proof"] is True
    assert peer["payload_sent"] is False
    assert peer["identity_plan"]["unauthorized_uid"] == 2000
    assert peer["identity_plan"]["primary_gid"] == 2000
    assert peer["identity_plan"]["supplementary_gids"] == [4110]
    assert peer["identity_plan"]["creates_persistent_identity"] is False

    invariants = evidence["promotion_invariants"]
    assert invariants["campaign_state"] == "BLOCKED"
    assert invariants["promotion_recommendation"] == "HOLD"
    assert invariants["promotion_allowed"] is False
    assert invariants["runtime_status"] == "NOT_RUN"
    assert invariants["execution_authority"] == "none"
    assert invariants["payload_sent"] is False
    assert invariants["persistent_state_created"] is False

    assert "CURRENT_PID_USER_NAMESPACE_MAPPING" in evidence["resolved_by_this_evidence"]
    assert "UNAUTHORIZED_PEER_NEGATIVE" in evidence["resolved_by_this_evidence"]
    assert "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED" in evidence["remaining_lab_l1_blockers"]
    assert "RUNNER_AUTHORIZATION_TRUST_STORE_ABSENT" in evidence["remaining_lab_l1_blockers"]

    sanitization = evidence["sanitization"]
    assert all(value is False for value in sanitization.values())


def test_chg072_change_record_tracks_runtime_evidence_without_promotion() -> None:
    record = yaml.safe_load(CHG072_PATH.read_text(encoding="utf-8"))
    assert record["id"] == "CHG-HSL-072"
    assert record["classification"] == "HARDENING"
    assert record["state"] == "ACCEPTED"
    assert record["source"]["campaign"] == "VAL-HSL-RUNNER-L1-LIVE-PROMOTION"
    assert record["source"]["observation"] == "OBS-RUNNER-POLICY-PROMOTION"
    assert record["issue"] == 402
    assert record["validation"]["targeted"] == "PASS"
    assert record["validation"]["regression"] == "PASS"
    assert record["validation"]["security"] == "PASS"
    assert record["validation"]["runtime"] == "PASS"
    assert record["promotion"]["commit"] is None
    assert record["promotion"]["artifactDigest"] is None


def test_chg038_live_observation_is_preserved_as_historical_evidence() -> None:
    evidence = yaml.safe_load(CHG038_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["change_record"] == "CHG-HSL-038"
    assert evidence["promotion"]["promotion_allowed"] is False
    assert evidence["promotion"]["runtime_status"] == "NOT_RUN"
    assert evidence["user_namespace_observation"]["result"] == "PASS"
    assert evidence["user_namespace_observation"]["observed"]["gateway"]["pid"] == 3649254
    assert evidence["user_namespace_observation"]["observed"]["runner"]["pid"] == 3367226
    assert evidence["host_identity_socket_observation"]["result"] == "FAIL_CLOSED"
    assert evidence["host_identity_socket_observation"]["observed"]["socket"]["present"] is True
    assert evidence["host_identity_socket_observation"]["observed"]["trust_store"]["present"] is False


def test_unknown_webgoat_rerun_is_never_reclassified() -> None:
    observation = _observations()["OBS-LIVE-EFFECT-RESET"]
    assert "result=UNKNOWN" in observation["evidence"]
    assert "live-runner-effect:NOT_RUN" in observation["evidence"]
    assert "live-terminal-evidence:NOT_RUN" in observation["evidence"]
    assert "live-audit-custody:NOT_RUN" in observation["evidence"]
    assert "post-effect-package:NOT_RUN" in observation["evidence"]


def test_status_doc_tracks_current_lifecycle_and_connector_state() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert f"**Current Labs baseline:** `{STATUS_BASELINE}`" in text
    assert f"**CHG-HSL-072 reconciliation base:** `{CHG072_RECONCILIATION_BASE}`" in text
    assert "GREEN-REPO is not live acceptance" in text
    assert "commit SHA is reconciliation provenance, not a runtime authority" in text
    assert "**DVWA live lifecycle acceptance:** `run_8f2174dc4c87452098b700ff556ac978`" in text
    assert "**Juice Shop live lifecycle acceptance:** `run_cc3cd41e85c44d9182305960ea816f18`" in text
    assert "The Hermes MCP control surface is currently **callable**" in text
    assert "CONNECTOR-LAST-ACCEPTED-CALLABLE / DVWA-AND-JUICE-LIFECYCLES-ACCEPTED" in text
    assert "ChatGPT connector exposure is an execution-context concern" in text
    assert "#393 DVWA and #394 Juice Shop are already accepted/closed" in text
    assert "execute issue #393" not in text
    assert "if #393 is PASS" not in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE" in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR" not in text


def test_status_doc_tracks_chg072_current_userns_and_peer_negative() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "CHG-HSL-071" in text
    assert "CHG-HSL-072" in text
    assert "HASH_CHAIN_SEAL` VERIFIED" in text
    assert "PRE_PROMOTION `ASSEMBLED / HOLD / INCOMPLETE`" in text
    assert "Current user-namespace re-attestation" in text
    assert "PASS / ACCEPTED-LIVE-OBSERVATION" in text
    assert "HOLD_REFUSAL_OBSERVED" in text
    assert "canonical_proof=true" in text
    assert "payload_sent=false" in text
    assert "Runner authorization trust store remains `OBSERVED_ABSENT`" in text
    assert "PROD-only readiness" in text
    assert "not current LAB_L1 blockers" in text


def test_status_doc_preserves_bridge_and_historical_reobservation_provenance() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`" in text
    assert "accepted current live Bridge observation is `3717bd5469b061a44294b27e1a7510d477d3752b`" in text
    assert "7e4b6b1cd70ddda418f840f54ae7ecef30df52e9" in text
    assert "never promoted to \"current\"" in text
    assert "Gateway PID identity `4100`" in text
    assert "Runner PID identity `4101`" in text
    assert "owner `4101:4110`; mode `0660`" in text
    assert "OBSERVED_ABSENT" in text
    assert "`0 0 4294967295`" in text
    assert "historical observation remains explicitly **NOT re-attested**" in text


def test_status_doc_retains_locked_invariants() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    for invariant in (
        "LAB_L1",
        "BLOCKED",
        "HOLD",
        "promotion_allowed=false",
        "runtime_status=NOT_RUN",
        "execution_authority=none",
        "supplier_selection=NO_SELECTION",
        "trust-store=ABSENT",
    ):
        assert invariant in text, invariant


def test_epic10_still_does_not_claim_live_tenant_isolation() -> None:
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
