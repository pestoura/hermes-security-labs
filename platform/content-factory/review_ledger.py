from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
DECISIONS = {"APPROVE", "REJECT"}
PROMOTION_TARGETS = {"LAB_VALIDATED", "CANDIDATE", "STABLE"}


class ReviewLedgerError(ValueError):
    """Fail-closed local content-governance violation."""


def _load_factory():
    name = "_hex0r_content_factory_contract"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / "content_factory.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot load content factory contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


factory = _load_factory()


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _atomic_create(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ReviewLedgerError("immutable ledger path collision")
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _candidate_seed(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": candidate.get("kind"),
        "source_events": candidate.get("source_events"),
        "reuse_strategy": candidate.get("reuse_strategy"),
        "metrics": candidate.get("metrics"),
        "duplicate_of": None,
    }


def _validate_fresh_candidate(candidate: Mapping[str, Any]) -> None:
    if not isinstance(candidate, Mapping):
        raise ReviewLedgerError("candidate must be a mapping")
    if candidate.get("lifecycle") != "PROPOSED":
        raise ReviewLedgerError("only fresh proposed candidates may enter the ledger")
    if candidate.get("human_reviewed") is not False or candidate.get("auto_merge") is not False:
        raise ReviewLedgerError("caller cannot pre-approve or auto-merge a candidate")
    if candidate.get("duplicate_of") is not None:
        raise ReviewLedgerError("duplicate classification is ledger-owned")
    seed = _candidate_seed(candidate)
    expected = f"cc_{factory._digest(seed)[:32]}"
    if candidate.get("candidate_id") != expected:
        raise ReviewLedgerError("candidate identity does not match canonical content")
    factory.promotion_failures(candidate, target="LAB_VALIDATED")


def _review_identity(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("review_receipt_id", None)
    return f"rv_{hashlib.sha256(_canonical(unsigned)).hexdigest()[:32]}"


def _promotion_identity(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("promotion_receipt_id", None)
    return f"pm_{hashlib.sha256(_canonical(unsigned)).hexdigest()[:32]}"


class LocalReviewLedger:
    """Controlled-local append-only evidence for content review and promotion.

    It does not merge content, execute labs, build images, deploy detections or grant
    execution authority. It records governance decisions over repository candidates.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.candidates = self.root / "candidates"
        self.reviews = self.root / "reviews"
        self.promotions = self.root / "promotions"
        self.duplicates = self.root / "duplicates"
        for path in (self.root, self.candidates, self.reviews, self.promotions, self.duplicates):
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o700)

    def register(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        _validate_fresh_candidate(candidate)
        candidate_id = str(candidate["candidate_id"])
        payload = _canonical(candidate)
        digest = hashlib.sha256(payload).hexdigest()
        path = self.candidates / f"{candidate_id}.json"
        if path.exists():
            if path.read_bytes() != payload:
                raise ReviewLedgerError("candidate identity collision")
            receipt = {
                "schema_version": "1.0",
                "result": "BLOCKED_DUPLICATE",
                "candidate_id": candidate_id,
                "duplicate_of": candidate_id,
                "candidate_sha256": digest,
                "auto_merge": False,
                "execution_authority": "NONE",
            }
            receipt_id = hashlib.sha256(_canonical(receipt)).hexdigest()
            _atomic_create(self.duplicates / f"{receipt_id}.json", _canonical(receipt))
            return receipt

        _atomic_create(path, payload)
        return {
            "schema_version": "1.0",
            "result": "REGISTERED",
            "candidate_id": candidate_id,
            "duplicate_of": None,
            "candidate_sha256": digest,
            "auto_merge": False,
            "execution_authority": "NONE",
        }

    def record_review(
        self,
        candidate_id: str,
        *,
        reviewer: str,
        decision: str,
        rationale: str,
        reviewed_at: str,
    ) -> dict[str, Any]:
        candidate = self._candidate(candidate_id)
        if not ID.fullmatch(reviewer) or decision not in DECISIONS:
            raise ReviewLedgerError("invalid reviewer or review decision")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 2048:
            raise ReviewLedgerError("bounded review rationale is required")
        if not isinstance(reviewed_at, str) or not reviewed_at.endswith("Z"):
            raise ReviewLedgerError("review timestamp must be explicit UTC")
        receipt = {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "candidate_sha256": _sha(candidate),
            "reviewer": reviewer,
            "decision": decision,
            "rationale": rationale,
            "reviewed_at": reviewed_at,
            "auto_merge": False,
            "execution_authority": "NONE",
        }
        receipt["review_receipt_id"] = _review_identity(receipt)
        _atomic_create(self.reviews / f"{receipt['review_receipt_id']}.json", _canonical(receipt))
        return receipt

    def promote(self, candidate_id: str, *, target: str, review_receipt_id: str) -> dict[str, Any]:
        if target not in PROMOTION_TARGETS:
            raise ReviewLedgerError("unsupported controlled promotion target")
        candidate = self._candidate(candidate_id)
        if not self.verify_review(review_receipt_id):
            raise ReviewLedgerError("review receipt integrity verification failed")
        review = self._receipt(self.reviews, review_receipt_id)
        if review.get("candidate_id") != candidate_id or review.get("candidate_sha256") != _sha(candidate):
            raise ReviewLedgerError("review receipt is not bound to candidate")
        if review.get("decision") != "APPROVE":
            raise ReviewLedgerError("promotion requires recorded human approval")

        reviewed = factory.record_human_review(candidate, reviewer=str(review["reviewer"]))
        try:
            promoted = factory.promote(reviewed, target=target)
        except Exception as exc:
            raise ReviewLedgerError("promotion gates failed") from exc
        receipt = {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "candidate_sha256": _sha(candidate),
            "review_receipt_id": review_receipt_id,
            "target": target,
            "result": "PROMOTION_ELIGIBLE",
            "auto_merge": False,
            "execution_authority": "NONE",
            "promoted_candidate_sha256": _sha(promoted),
        }
        receipt["promotion_receipt_id"] = _promotion_identity(receipt)
        _atomic_create(self.promotions / f"{receipt['promotion_receipt_id']}.json", _canonical(receipt))
        return receipt

    def verify_review(self, review_receipt_id: str) -> bool:
        try:
            review = self._receipt(self.reviews, review_receipt_id)
            if review.get("review_receipt_id") != review_receipt_id:
                return False
            if _review_identity(review) != review_receipt_id:
                return False
            if review.get("decision") not in DECISIONS or review.get("auto_merge") is not False:
                return False
            if review.get("execution_authority") != "NONE":
                return False
            candidate = self._candidate(str(review["candidate_id"]))
            return review.get("candidate_sha256") == _sha(candidate)
        except (ReviewLedgerError, KeyError, OSError, json.JSONDecodeError):
            return False

    def verify_promotion(self, promotion_receipt_id: str) -> bool:
        try:
            receipt = self._receipt(self.promotions, promotion_receipt_id)
            return (
                receipt.get("promotion_receipt_id") == promotion_receipt_id
                and _promotion_identity(receipt) == promotion_receipt_id
                and receipt.get("result") == "PROMOTION_ELIGIBLE"
                and receipt.get("auto_merge") is False
                and receipt.get("execution_authority") == "NONE"
                and self.verify_review(str(receipt["review_receipt_id"]))
            )
        except (ReviewLedgerError, KeyError, OSError, json.JSONDecodeError):
            return False

    def _candidate(self, candidate_id: str) -> dict[str, Any]:
        if not isinstance(candidate_id, str) or not candidate_id.startswith("cc_"):
            raise ReviewLedgerError("invalid candidate id")
        try:
            value = json.loads((self.candidates / f"{candidate_id}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewLedgerError("candidate unavailable") from exc
        _validate_fresh_candidate(value)
        return value

    @staticmethod
    def _receipt(directory: Path, receipt_id: str) -> dict[str, Any]:
        if not isinstance(receipt_id, str) or not ID.fullmatch(receipt_id):
            raise ReviewLedgerError("invalid receipt id")
        try:
            value = json.loads((directory / f"{receipt_id}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewLedgerError("receipt unavailable") from exc
        if not isinstance(value, dict):
            raise ReviewLedgerError("invalid receipt")
        return value
