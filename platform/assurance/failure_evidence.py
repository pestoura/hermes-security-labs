"""Evidence-bound chaos/failure-suite validation for SVP2-D-02."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

FAILURE_CASES = {
    "restart", "invalid_json", "empty_stdout", "timeout", "network_loss",
    "disk_full", "partial_cleanup", "concurrency", "cancellation", "incompatible_version",
}
EVIDENCE_ID = re.compile(r"^ev_[A-Za-z0-9._:-]{8,128}$")


class FailureEvidenceError(ValueError):
    pass


def validate_failure_evidence(results: Mapping[str, Mapping[str, Any]]) -> str:
    if not isinstance(results, Mapping):
        raise FailureEvidenceError("FAILURE_EVIDENCE_REQUIRED")
    missing = FAILURE_CASES.difference(results)
    unknown = set(results).difference(FAILURE_CASES)
    if missing:
        raise FailureEvidenceError(f"MISSING_FAILURE_CASES:{','.join(sorted(missing))}")
    if unknown:
        raise FailureEvidenceError(f"UNKNOWN_FAILURE_CASES:{','.join(sorted(unknown))}")

    normalized: dict[str, dict[str, str]] = {}
    seen_evidence: set[str] = set()
    for name in sorted(FAILURE_CASES):
        record = results[name]
        if not isinstance(record, Mapping) or record.get("status") != "pass":
            raise FailureEvidenceError(f"FAILURE_CASE_NOT_PASSING:{name}")
        evidence_id = record.get("evidence_id")
        if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(evidence_id):
            raise FailureEvidenceError(f"FAILURE_EVIDENCE_ID_INVALID:{name}")
        if evidence_id in seen_evidence:
            raise FailureEvidenceError("FAILURE_EVIDENCE_REUSE_DETECTED")
        seen_evidence.add(evidence_id)
        observed_at = record.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.endswith("Z"):
            raise FailureEvidenceError(f"FAILURE_OBSERVATION_TIMESTAMP_INVALID:{name}")
        normalized[name] = {"status": "pass", "evidence_id": evidence_id, "observed_at": observed_at}

    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
