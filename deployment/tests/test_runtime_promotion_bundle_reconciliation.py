"""Pin the WebGoat L1 promotion bundle repository prerequisites.

These tests prevent repository readiness from silently dropping accepted audit,
host, user-namespace, signer-attestation, durable-backend, tenant-isolation,
live-evidence-package or Runner service-composition boundaries. They do not
authorize runtime promotion or claim that any live observation ran.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "deployment" / "runtime-promotion" / "runtime_promotion_evidence_gate.py"
BUNDLE_PATH = ROOT / "deployment" / "runtime-promotion" / "runtime-promotion-evidence-bundle.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("runtime_promotion_bundle_reconciliation_test", GATE_PATH)

REQUIRED_CHANGES = {
    "CHG-HSL-015",
    "CHG-HSL-016",
    "CHG-HSL-017",
    "CHG-HSL-020",
    "CHG-HSL-022",
    "CHG-HSL-025",
    "CHG-HSL-028",
    "CHG-HSL-031",
}

REQUIRED_COMPONENTS = {
    "platform/runner-dispatch/audit.py",
    "platform/evidence-plane/dispatch_audit_custody.py",
    "deployment/runtime-promotion/runtime_host_evidence.py",
    "deployment/runtime-promotion/runtime-host-evidence-descriptor.schema.json",
    "deployment/runtime-promotion/runtime_userns_evidence.py",
    "deployment/runtime-promotion/runtime-userns-evidence-descriptor.schema.json",
    "deployment/runtime-promotion/runtime_signer_attestation.py",
    "deployment/runtime-promotion/tb1-signer-attestation.schema.json",
    "deployment/runtime-promotion/runtime_evidence_backend_attestation.py",
    "deployment/runtime-promotion/evidence-backend-attestation.schema.json",
    "deployment/runtime-promotion/runtime_evidence_backend_tenant_isolation.py",
    "deployment/runtime-promotion/evidence-backend-tenant-isolation-attestation.schema.json",
    "deployment/runtime-promotion/runtime_live_promotion_evidence.py",
    "deployment/runtime-promotion/live-promotion-evidence-package.schema.json",
    "platform/runner-service/service_composition.py",
}

REQUIRED_POLICIES = {
    "platform/evidence-plane/dispatch-audit-policy.yaml",
    "platform/runner-service/composition-policy.yaml",
}


def _bundle() -> dict[str, Any]:
    document = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_bundle_pins_current_repository_prerequisites() -> None:
    bundle = _bundle()
    assert REQUIRED_CHANGES <= set(bundle["required_change_records"])
    assert REQUIRED_COMPONENTS <= set(bundle["required_components"])
    assert REQUIRED_POLICIES <= set(bundle["fail_closed_policies"])


def test_required_change_records_are_accepted_without_runtime_claim() -> None:
    for change_id in REQUIRED_CHANGES:
        path = ROOT / "changes" / f"{change_id}.yaml"
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert record["state"] == "ACCEPTED"
        assert record["validation"]["targeted"] == "PASS"
        assert record["validation"]["regression"] == "PASS"
        assert record["validation"]["security"] == "PASS"
        assert record["validation"]["runtime"] == "NOT_RUN"
        assert gate._change_record_findings(change_id) == []


def test_required_policies_remain_fail_closed() -> None:
    for value in REQUIRED_POLICIES:
        path = ROOT / value
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert gate._policy_findings(path, policy) == []


def test_reconciled_bundle_is_repository_ready_but_never_promotes() -> None:
    result = gate.run_gate(gate.load_bundle(BUNDLE_PATH))
    assert result.repository_ready is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"


def test_signer_attestation_is_a_repository_prerequisite_not_live_evidence() -> None:
    bundle = _bundle()
    assert "CHG-HSL-022" in bundle["required_change_records"]
    assert (
        "deployment/runtime-promotion/runtime_signer_attestation.py"
        in bundle["required_components"]
    )
    assert (
        "deployment/runtime-promotion/tb1-signer-attestation.schema.json"
        in bundle["required_components"]
    )
    record = yaml.safe_load(
        (ROOT / "changes" / "CHG-HSL-022.yaml").read_text(encoding="utf-8")
    )
    assert record["validation"]["runtime"] == "NOT_RUN"


def test_backend_attestation_is_a_repository_prerequisite_not_live_backend_proof() -> None:
    bundle = _bundle()
    assert "CHG-HSL-025" in bundle["required_change_records"]
    assert (
        "deployment/runtime-promotion/runtime_evidence_backend_attestation.py"
        in bundle["required_components"]
    )
    assert (
        "deployment/runtime-promotion/evidence-backend-attestation.schema.json"
        in bundle["required_components"]
    )
    record = yaml.safe_load(
        (ROOT / "changes" / "CHG-HSL-025.yaml").read_text(encoding="utf-8")
    )
    assert record["validation"]["runtime"] == "NOT_RUN"


def test_tenant_isolation_is_a_repository_prerequisite_not_live_proof() -> None:
    bundle = _bundle()
    assert "CHG-HSL-028" in bundle["required_change_records"]
    assert (
        "deployment/runtime-promotion/runtime_evidence_backend_tenant_isolation.py"
        in bundle["required_components"]
    )
    assert (
        "deployment/runtime-promotion/evidence-backend-tenant-isolation-attestation.schema.json"
        in bundle["required_components"]
    )
    record = yaml.safe_load(
        (ROOT / "changes" / "CHG-HSL-028.yaml").read_text(encoding="utf-8")
    )
    assert record["validation"]["runtime"] == "NOT_RUN"


def test_live_package_verifier_is_required_but_live_package_is_not_committed() -> None:
    bundle = _bundle()
    assert "CHG-HSL-031" in bundle["required_change_records"]
    assert (
        "deployment/runtime-promotion/runtime_live_promotion_evidence.py"
        in bundle["required_components"]
    )
    assert (
        "deployment/runtime-promotion/live-promotion-evidence-package.schema.json"
        in bundle["required_components"]
    )
    assert (
        "deployment/runtime-promotion/templates/live-promotion-evidence-package.example.yaml"
        not in bundle["required_components"]
    )
    record = yaml.safe_load(
        (ROOT / "changes" / "CHG-HSL-031.yaml").read_text(encoding="utf-8")
    )
    assert record["validation"]["runtime"] == "NOT_RUN"


def test_bundle_does_not_require_reconciliation_change_records() -> None:
    required = set(_bundle()["required_change_records"])
    for change_id in (
        "CHG-HSL-018",
        "CHG-HSL-021",
        "CHG-HSL-023",
        "CHG-HSL-026",
        "CHG-HSL-029",
        "CHG-HSL-032",
    ):
        assert change_id not in required
