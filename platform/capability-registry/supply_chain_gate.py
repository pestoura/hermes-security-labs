"""Cryptographic identity binding for C-02 capability supply-chain evidence.

Repository-side contract only. It validates evidence already produced by external
SBOM/signing/provenance/scanning systems and does not generate or trust such evidence
by itself.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class SupplyChainGateError(ValueError):
    pass


def validate_stable_supply_chain(evidence: Mapping[str, Any]) -> None:
    if not isinstance(evidence, Mapping):
        raise SupplyChainGateError("SUPPLY_CHAIN_EVIDENCE_REQUIRED")
    subject = evidence.get("subject_digest")
    if not isinstance(subject, str) or not DIGEST.fullmatch(subject):
        raise SupplyChainGateError("SUBJECT_DIGEST_INVALID")

    for name in ("sbom", "signature", "provenance"):
        attestation = evidence.get(name)
        if not isinstance(attestation, Mapping):
            raise SupplyChainGateError(f"{name.upper()}_EVIDENCE_REQUIRED")
        if attestation.get("verified") is not True:
            raise SupplyChainGateError(f"{name.upper()}_NOT_VERIFIED")
        if attestation.get("subject_digest") != subject:
            raise SupplyChainGateError(f"{name.upper()}_SUBJECT_MISMATCH")
        artifact_digest = attestation.get("artifact_digest")
        if not isinstance(artifact_digest, str) or not DIGEST.fullmatch(artifact_digest):
            raise SupplyChainGateError(f"{name.upper()}_ARTIFACT_DIGEST_INVALID")

    scan = evidence.get("scan")
    if not isinstance(scan, Mapping):
        raise SupplyChainGateError("SCAN_EVIDENCE_REQUIRED")
    if scan.get("subject_digest") != subject:
        raise SupplyChainGateError("SCAN_SUBJECT_MISMATCH")
    blockers = scan.get("blockers")
    if isinstance(blockers, bool) or not isinstance(blockers, int) or blockers < 0:
        raise SupplyChainGateError("SCAN_BLOCKERS_INVALID")
    if blockers != 0:
        raise SupplyChainGateError("SCAN_BLOCKERS_PRESENT")


def stable_supply_chain_allowed(evidence: Mapping[str, Any]) -> bool:
    try:
        validate_stable_supply_chain(evidence)
        return True
    except SupplyChainGateError:
        return False
