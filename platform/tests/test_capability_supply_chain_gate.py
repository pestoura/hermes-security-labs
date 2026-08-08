from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/capability-registry/supply_chain_gate.py"
spec = importlib.util.spec_from_file_location("capability_supply_chain_gate", PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

SUBJECT = "sha256:" + "a" * 64


def _attestation(seed: str) -> dict:
    return {
        "verified": True,
        "subject_digest": SUBJECT,
        "artifact_digest": "sha256:" + seed * 64,
    }


def _evidence() -> dict:
    return {
        "subject_digest": SUBJECT,
        "sbom": _attestation("b"),
        "signature": _attestation("c"),
        "provenance": _attestation("d"),
        "scan": {"subject_digest": SUBJECT, "blockers": 0},
    }


def test_all_verified_evidence_bound_to_same_subject_allows_stable_gate() -> None:
    value = _evidence()
    gate.validate_stable_supply_chain(value)
    assert gate.stable_supply_chain_allowed(value) is True


@pytest.mark.parametrize("name", ["sbom", "signature", "provenance"])
def test_unverified_attestation_fails_closed(name: str) -> None:
    value = _evidence()
    value[name]["verified"] = False
    with pytest.raises(gate.SupplyChainGateError, match=f"{name.upper()}_NOT_VERIFIED"):
        gate.validate_stable_supply_chain(value)


def test_attestation_for_different_image_cannot_be_reused() -> None:
    value = _evidence()
    value["signature"]["subject_digest"] = "sha256:" + "e" * 64
    with pytest.raises(gate.SupplyChainGateError, match="SIGNATURE_SUBJECT_MISMATCH"):
        gate.validate_stable_supply_chain(value)


def test_scan_blocker_prevents_stable_promotion_evidence() -> None:
    value = _evidence()
    value["scan"]["blockers"] = 1
    with pytest.raises(gate.SupplyChainGateError, match="SCAN_BLOCKERS_PRESENT"):
        gate.validate_stable_supply_chain(value)


def test_non_sha256_artifact_identity_is_rejected() -> None:
    value = _evidence()
    value["sbom"]["artifact_digest"] = "artifact://sbom"
    with pytest.raises(gate.SupplyChainGateError, match="SBOM_ARTIFACT_DIGEST_INVALID"):
        gate.validate_stable_supply_chain(value)
