from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXT_DIR = ROOT / "platform" / "extensions"

spec = importlib.util.spec_from_file_location("extension_conformance", EXT_DIR / "conformance.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

ExtensionConformanceError = module.ExtensionConformanceError
activation_allowed = module.activation_allowed
activation_failures = module.activation_failures
certify = module.certify
quarantine = module.quarantine
revoke = module.revoke
validate_manifest = module.validate_manifest


def _manifest(**overrides):
    value = {
        "schema_version": "1.0",
        "extension_id": "ext-synthetic-evaluator",
        "kind": "evaluator",
        "version": "1.0.0",
        "protocol_version": "2.0",
        "permissions": ["evidence:read", "knowledge:read"],
        "signature": {
            "state": "verified",
            "signer": "synthetic-test-signer",
            "artifact_sha256": "b" * 64,
        },
        "compatibility": {"compatible": True, "contract_version": "2.0"},
        "conformance": {"passed": True, "suite_version": "1.0", "report_sha256": "c" * 64},
        "lifecycle": "candidate",
    }
    value.update(overrides)
    return value


def test_manifest_validates_against_schema() -> None:
    schema = json.loads((EXT_DIR / "extension-manifest.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(_manifest())


def test_all_five_sdk_families_are_fixed_and_supported() -> None:
    assert module.EXTENSION_KINDS == {
        "capability-runner",
        "runtime-driver",
        "lab-driver",
        "evidence-adapter",
        "evaluator",
    }


def test_candidate_is_not_activation_eligible_even_with_green_evidence() -> None:
    manifest = _manifest()
    assert activation_allowed(manifest) is False
    assert activation_failures(manifest) == ["lifecycle"]


def test_certification_requires_signature_compatibility_and_conformance() -> None:
    certified = certify(_manifest())
    assert certified["lifecycle"] == "certified"
    assert activation_allowed(certified) is True

    with pytest.raises(ExtensionConformanceError):
        certify(_manifest(signature={"state": "unverified", "signer": "synthetic", "artifact_sha256": "d" * 64}))
    with pytest.raises(ExtensionConformanceError):
        certify(_manifest(compatibility={"compatible": False, "contract_version": "2.0"}))
    with pytest.raises(ExtensionConformanceError):
        certify(_manifest(conformance={"passed": False, "suite_version": "1.0", "report_sha256": "e" * 64}))


def test_permissions_must_be_explicit_unique_and_known() -> None:
    validate_manifest(_manifest(permissions=[]))
    with pytest.raises(ExtensionConformanceError):
        validate_manifest(_manifest(permissions=["evidence:read", "evidence:read"]))
    with pytest.raises(ExtensionConformanceError):
        validate_manifest(_manifest(permissions=["unbounded:host-control"]))


@pytest.mark.parametrize("field", ["command", "argv", "shell", "cwd", "environment", "executable", "entrypoint"])
def test_command_shaped_fields_are_refused(field: str) -> None:
    manifest = _manifest()
    manifest[field] = "synthetic-value"
    with pytest.raises(ExtensionConformanceError):
        validate_manifest(manifest)


def test_quarantine_and_revocation_fail_closed() -> None:
    certified = certify(_manifest())
    quarantined = quarantine(certified)
    assert activation_allowed(quarantined) is False
    with pytest.raises(ExtensionConformanceError):
        certify(quarantined)

    revoked = revoke(certified)
    assert revoked["signature"]["state"] == "revoked"
    assert activation_allowed(revoked) is False
    with pytest.raises(ExtensionConformanceError):
        certify(revoked)


def test_policy_preserves_nonproduction_boundary() -> None:
    policy = yaml.safe_load((EXT_DIR / "extension-policy.yaml").read_text())
    assert policy["activation"]["generic_execution_fields_forbidden"] is True
    assert policy["runtime_status"] == {
        "production_signature_verification": "NOT_RUN",
        "extension_loading": "NOT_RUN",
        "runtime_isolation": "NOT_RUN",
        "production_certification": "NOT_RUN",
        "third_party_extension_execution": "NOT_RUN",
    }
