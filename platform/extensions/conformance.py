from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

EXTENSION_KINDS = {
    "capability-runner",
    "runtime-driver",
    "lab-driver",
    "evidence-adapter",
    "evaluator",
}
PERMISSIONS = {
    "network:outbound",
    "evidence:read",
    "evidence:write",
    "lab:read",
    "lab:control",
    "runtime:read",
    "runtime:control",
    "filesystem:temp",
    "knowledge:read",
}
LIFECYCLE_STATES = {"candidate", "certified", "quarantined", "deprecated", "revoked"}
FORBIDDEN_EXECUTION_FIELDS = {"command", "argv", "shell", "cwd", "environment", "executable", "entrypoint"}


class ExtensionConformanceError(ValueError):
    """Fail-closed extension conformance contract violation."""


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("kind") not in EXTENSION_KINDS:
        raise ExtensionConformanceError("unsupported extension kind")
    if manifest.get("lifecycle") not in LIFECYCLE_STATES:
        raise ExtensionConformanceError("unsupported lifecycle state")

    unknown_execution_fields = FORBIDDEN_EXECUTION_FIELDS.intersection(manifest)
    if unknown_execution_fields:
        raise ExtensionConformanceError("command-shaped extension fields are forbidden")

    permissions = manifest.get("permissions")
    if not isinstance(permissions, list) or len(set(permissions)) != len(permissions):
        raise ExtensionConformanceError("permissions must be an explicit unique list")
    if set(permissions).difference(PERMISSIONS):
        raise ExtensionConformanceError("unknown extension permission")

    signature = manifest.get("signature")
    compatibility = manifest.get("compatibility")
    conformance = manifest.get("conformance")
    if not all(isinstance(value, Mapping) for value in (signature, compatibility, conformance)):
        raise ExtensionConformanceError("incomplete extension evidence")

    if signature.get("state") not in {"verified", "unverified", "invalid", "revoked"}:
        raise ExtensionConformanceError("unknown signature state")
    if not signature.get("signer") or len(str(signature.get("artifact_sha256", ""))) != 64:
        raise ExtensionConformanceError("incomplete signature evidence")
    if not compatibility.get("contract_version"):
        raise ExtensionConformanceError("compatibility contract version is required")
    if not conformance.get("suite_version") or len(str(conformance.get("report_sha256", ""))) != 64:
        raise ExtensionConformanceError("incomplete conformance evidence")


def activation_failures(manifest: Mapping[str, Any]) -> list[str]:
    validate_manifest(manifest)
    failures: list[str] = []
    signature = manifest["signature"]
    compatibility = manifest["compatibility"]
    conformance = manifest["conformance"]

    if signature.get("state") != "verified":
        failures.append("signature")
    if compatibility.get("compatible") is not True:
        failures.append("compatibility")
    if conformance.get("passed") is not True:
        failures.append("conformance")
    if manifest.get("lifecycle") != "certified":
        failures.append("lifecycle")
    return sorted(failures)


def activation_allowed(manifest: Mapping[str, Any]) -> bool:
    try:
        return not activation_failures(manifest)
    except ExtensionConformanceError:
        return False


def certify(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    if manifest.get("lifecycle") in {"quarantined", "revoked", "deprecated"}:
        raise ExtensionConformanceError("non-active lifecycle cannot be certified")

    candidate = deepcopy(dict(manifest))
    candidate["lifecycle"] = "certified"
    failures = activation_failures(candidate)
    if failures:
        raise ExtensionConformanceError(f"certification gates failed: {','.join(failures)}")
    return candidate


def quarantine(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    value = deepcopy(dict(manifest))
    value["lifecycle"] = "quarantined"
    return value


def revoke(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    value = deepcopy(dict(manifest))
    value["lifecycle"] = "revoked"
    signature = deepcopy(dict(value["signature"]))
    signature["state"] = "revoked"
    value["signature"] = signature
    return value
