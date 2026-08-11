"""Pin the post-composition WebGoat L1 promotion bundle prerequisites.

These tests prevent repository readiness from silently dropping accepted audit,
host, user-namespace or Runner service-composition boundaries. They do not
authorize runtime promotion.
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
}

REQUIRED_COMPONENTS = {
    "platform/runner-dispatch/audit.py",
    "platform/evidence-plane/dispatch_audit_custody.py",
    "deployment/runtime-promotion/runtime_host_evidence.py",
    "deployment/runtime-promotion/runtime-host-evidence-descriptor.schema.json",
    "deployment/runtime-promotion/runtime_userns_evidence.py",
    "deployment/runtime-promotion/runtime-userns-evidence-descriptor.schema.json",
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


def test_bundle_pins_post_composition_repository_prerequisites() -> None:
    bundle = _bundle()
    assert REQUIRED_CHANGES <= set(bundle["required_change_records"])
    assert REQUIRED_COMPONENTS <= set(bundle["required_components"])
    assert REQUIRED_POLICIES <= set(bundle["fail_closed_policies"])


def test_new_change_records_are_accepted_without_runtime_claim() -> None:
    for change_id in REQUIRED_CHANGES:
        path = ROOT / "changes" / f"{change_id}.yaml"
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert record["state"] == "ACCEPTED"
        assert record["validation"]["targeted"] == "PASS"
        assert record["validation"]["regression"] == "PASS"
        assert record["validation"]["security"] == "PASS"
        assert record["validation"]["runtime"] == "NOT_RUN"
        assert gate._change_record_findings(change_id) == []


def test_new_policies_remain_fail_closed() -> None:
    for value in REQUIRED_POLICIES:
        path = ROOT / value
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert gate._policy_findings(path, policy) == []


def test_reconciled_bundle_is_repository_ready_but_never_promotes() -> None:
    result = gate.run_gate(gate.load_bundle(BUNDLE_PATH))
    assert result.repository_ready is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"


def test_bundle_does_not_require_reconciliation_change_records() -> None:
    # Requiring the Change Record that governs a bundle reconciliation inside the
    # same bundle would create a validation cycle while that record is still open.
    required = set(_bundle()["required_change_records"])
    assert "CHG-HSL-018" not in required
    assert "CHG-HSL-021" not in required
