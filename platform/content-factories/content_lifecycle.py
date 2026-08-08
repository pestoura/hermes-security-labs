"""Fail-closed lifecycle gates for continuous content factories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ORDER = (
    "PROPOSED", "TRIAGED", "GENERATED", "STATIC_VALIDATED", "LAB_VALIDATED",
    "REVIEWED", "CANDIDATE", "ACCEPTED", "ACTIVE",
)
EXCEPTION_STATES = {"REJECTED", "DUPLICATE", "SUPERSEDED", "DEPRECATED", "QUARANTINED"}


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    next_state: str
    codes: tuple[str, ...]


def evaluate_promotion(
    *,
    current_state: str,
    target_state: str,
    fingerprint: str,
    active_fingerprints: Iterable[str],
    positive_control_passed: bool,
    negative_control_passed: bool,
    human_review_id: str | None = None,
    pr_approval_id: str | None = None,
) -> PromotionDecision:
    if current_state not in ORDER or target_state not in ORDER:
        return PromotionDecision(False, current_state, ("STATE_INVALID",))
    if current_state == "ACTIVE":
        return PromotionDecision(False, current_state, ("NON_SEQUENTIAL_TRANSITION",))
    expected = ORDER[ORDER.index(current_state) + 1]
    if target_state != expected:
        return PromotionDecision(False, current_state, ("NON_SEQUENTIAL_TRANSITION",))
    if not fingerprint:
        return PromotionDecision(False, current_state, ("FINGERPRINT_REQUIRED",))
    if fingerprint in set(active_fingerprints):
        return PromotionDecision(False, "DUPLICATE", ("DUPLICATE_BLOCKED",))
    if target_state in {"REVIEWED", "CANDIDATE", "ACCEPTED", "ACTIVE"}:
        if not (positive_control_passed and negative_control_passed):
            return PromotionDecision(False, current_state, ("LAB_CONTROLS_INCOMPLETE",))
    if current_state == "REVIEWED" and target_state == "CANDIDATE" and not human_review_id:
        return PromotionDecision(False, current_state, ("HUMAN_REVIEW_REQUIRED",))
    if current_state == "CANDIDATE" and target_state == "ACCEPTED" and not pr_approval_id:
        return PromotionDecision(False, current_state, ("PR_APPROVAL_REQUIRED",))
    return PromotionDecision(True, target_state, ("PROMOTION_ALLOWED",))
