"""Strict evidence primitives for extension certification."""
from __future__ import annotations

import re
from typing import Any, Mapping

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CertificationEvidenceError(ValueError):
    pass


def validate_certification_evidence(manifest: Mapping[str, Any]) -> None:
    permissions = manifest.get("permissions")
    if not isinstance(permissions, list):
        raise CertificationEvidenceError("PERMISSIONS_NOT_EXPLICIT")

    signature = manifest.get("signature")
    conformance = manifest.get("conformance")
    compatibility = manifest.get("compatibility")
    if not all(isinstance(value, Mapping) for value in (signature, conformance, compatibility)):
        raise CertificationEvidenceError("CERTIFICATION_EVIDENCE_INCOMPLETE")

    artifact_digest = signature.get("artifact_sha256")
    report_digest = conformance.get("report_sha256")
    if not isinstance(artifact_digest, str) or not SHA256_RE.fullmatch(artifact_digest):
        raise CertificationEvidenceError("ARTIFACT_SHA256_INVALID")
    if not isinstance(report_digest, str) or not SHA256_RE.fullmatch(report_digest):
        raise CertificationEvidenceError("CONFORMANCE_REPORT_SHA256_INVALID")
    if signature.get("state") != "verified":
        raise CertificationEvidenceError("SIGNATURE_NOT_VERIFIED")
    if conformance.get("passed") is not True:
        raise CertificationEvidenceError("CONFORMANCE_NOT_PASSED")
    if compatibility.get("compatible") is not True:
        raise CertificationEvidenceError("CONTRACT_INCOMPATIBLE")
