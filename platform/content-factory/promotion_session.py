from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


factory = _load("_hex0r_content_factory_session", "content_factory.py")
ledger_mod = _load("_hex0r_content_review_ledger_session", "review_ledger.py")


class PromotionSessionError(ValueError):
    """Fail-closed orchestration error for a controlled content promotion session."""


def run_controlled_session(
    *,
    ledger_root: str | Path,
    candidate: Mapping[str, Any],
    reviewer: str,
    rationale: str,
    reviewed_at: str,
    target: str = "CANDIDATE",
) -> dict[str, Any]:
    """Register, review and assess one content candidate for promotion.

    The session records immutable local receipts only. It never merges a PR, deploys
    content, executes a lab or grants execution authority.
    """
    if target not in {"LAB_VALIDATED", "CANDIDATE"}:
        raise PromotionSessionError("controlled session target must be LAB_VALIDATED or CANDIDATE")

    ledger = ledger_mod.LocalReviewLedger(ledger_root)
    registration = ledger.register(candidate)
    if registration.get("result") != "REGISTERED":
        raise PromotionSessionError("candidate registration did not produce a fresh record")

    review = ledger.record_review(
        str(candidate.get("candidate_id", "")),
        reviewer=reviewer,
        decision="APPROVE",
        rationale=rationale,
        reviewed_at=reviewed_at,
    )
    if not ledger.verify_review(str(review.get("review_receipt_id", ""))):
        raise PromotionSessionError("review receipt verification failed")

    promotion = ledger.promote(
        str(candidate.get("candidate_id", "")),
        target=target,
        review_receipt_id=str(review["review_receipt_id"]),
    )
    if not ledger.verify_promotion(str(promotion.get("promotion_receipt_id", ""))):
        raise PromotionSessionError("promotion receipt verification failed")

    return {
        "schema_version": "1.0",
        "boundary": "CONTROLLED_LOCAL",
        "candidate_id": candidate["candidate_id"],
        "registration_result": registration["result"],
        "review_receipt_id": review["review_receipt_id"],
        "promotion_receipt_id": promotion["promotion_receipt_id"],
        "target": target,
        "promotion_result": promotion["result"],
        "auto_merge": False,
        "deployment_performed": False,
        "execution_authority": "NONE",
    }
