from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "platform/capability-registry"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controlled = _load("controlled_supply_chain_ci", REGISTRY / "controlled_supply_chain_ci.py")
gate = _load("supply_chain_gate_ci", REGISTRY / "supply_chain_gate.py")


def test_controlled_bundle_has_real_crypto_but_cannot_fake_missing_scan() -> None:
    artifact = (ROOT / "platform/runtime-base/runtime-base-policy.yaml").read_bytes()
    bundle = controlled.build_controlled_bundle(artifact=artifact, source_ref="controlled-ci")
    assert bundle["boundary"] == "CONTROLLED_CI"
    assert bundle["signature"]["verified"] is True
    assert bundle["signature"]["algorithm"] == "Ed25519"
    assert bundle["sbom"]["verified"] is True
    assert bundle["provenance"]["verified"] is True
    assert bundle["scan"]["status"] == "NOT_RUN"
    assert bundle["stable_promotion"] == "BLOCKED_UNTIL_SCAN_EVIDENCE"
    assert gate.stable_supply_chain_allowed(bundle) is False
    assert bundle["production_image"] == "NOT_RUN"
