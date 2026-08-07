from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CAP_DIR = ROOT / "platform" / "capability-registry"

spec = importlib.util.spec_from_file_location("capability_registry", CAP_DIR / "capability_registry.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

CapabilityRegistryError = module.CapabilityRegistryError
PROFILES = module.PROFILES
is_usable = module.is_usable
promote = module.promote
quarantine = module.quarantine
revoke = module.revoke
stable_gate_failures = module.stable_gate_failures
validate_capability = module.validate_capability


def _capability(**overrides):
    value = {
        "id": "synthetic.web-api",
        "profile": "web-api",
        "version": "1.0.0",
        "state": {"installed": True, "executable": True, "functionally_tested": True},
        "authorization": {"authorized": True, "policy_id": "authz/synthetic"},
        "compatibility": {"compatible": True, "protocol_version": "2.0"},
        "promotion": "candidate",
        "supply_chain": {
            "sbom": "artifact://sbom/synthetic",
            "signature": "artifact://signature/synthetic",
            "provenance": "artifact://provenance/synthetic",
            "scan_blockers": 0,
        },
        "revoked": False,
    }
    value.update(overrides)
    return value


def test_schema_accepts_canonical_candidate() -> None:
    schema = json.loads((CAP_DIR / "capability-registry.schema.json").read_text())
    registry = {"schema_version": "1.0", "registry_id": "synthetic", "capabilities": [_capability()]}
    jsonschema.Draft202012Validator(schema).validate(registry)


def test_profile_inventory_is_exact_and_fixed() -> None:
    assert PROFILES == {
        "web-api", "devsecops", "ai-mcp", "exploitation", "kubernetes",
        "identity", "cloud", "mobile", "iot-ot",
    }


def test_candidate_is_not_production_usable() -> None:
    assert is_usable(_capability()) is False


def test_all_stable_gates_are_required() -> None:
    stable = promote(_capability(), "stable")
    assert is_usable(stable) is True
    assert stable_gate_failures(stable) == []


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda c: c["state"].update(functionally_tested=False), "functionally_tested"),
        (lambda c: c["authorization"].update(authorized=False), "authorized"),
        (lambda c: c["compatibility"].update(compatible=False), "compatible"),
        (lambda c: c["supply_chain"].update(sbom=None), "sbom"),
        (lambda c: c["supply_chain"].update(signature=None), "signature"),
        (lambda c: c["supply_chain"].update(provenance=None), "provenance"),
        (lambda c: c["supply_chain"].update(scan_blockers=1), "scan_blockers"),
    ],
)
def test_stable_promotion_fails_closed_when_gate_missing(mutation, expected: str) -> None:
    capability = _capability()
    mutation(capability)
    with pytest.raises(CapabilityRegistryError, match=expected):
        promote(capability, "stable")


def test_quarantine_is_unusable_and_cannot_promote_directly_to_stable() -> None:
    value = quarantine(_capability(), reason="synthetic review required")
    assert value["promotion"] == "quarantined"
    assert is_usable(value) is False
    with pytest.raises(CapabilityRegistryError):
        promote(value, "stable")


def test_revocation_is_immediate_and_irreversible_by_promotion() -> None:
    stable = promote(_capability(), "stable")
    revoked = revoke(stable, reason="synthetic security event")
    assert revoked["revoked"] is True
    assert revoked["promotion"] == "revoked"
    assert is_usable(revoked) is False
    with pytest.raises(CapabilityRegistryError):
        promote(revoked, "candidate")


def test_unknown_profile_fails_closed() -> None:
    with pytest.raises(CapabilityRegistryError):
        validate_capability(_capability(profile="unknown"))


def test_runtime_supply_chain_operations_remain_not_run() -> None:
    policy = yaml.safe_load((CAP_DIR / "promotion-policy.yaml").read_text())
    assert policy["runtime_status"] == {
        "sbom_generation": "NOT_RUN",
        "signing": "NOT_RUN",
        "provenance_generation": "NOT_RUN",
        "image_scanning": "NOT_RUN",
        "production_revocation": "NOT_RUN",
        "image_promotion": "NOT_RUN",
    }
