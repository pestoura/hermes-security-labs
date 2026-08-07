from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RISK_DIR = ROOT / "platform" / "risk-findings"

spec = importlib.util.spec_from_file_location("risk_findings", RISK_DIR / "risk_findings.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

RiskFindingError = module.RiskFindingError
build_risk_assessment = module.build_risk_assessment
create_finding = module.create_finding
record_regression = module.record_regression
transition = module.transition


def _components():
    return {
        "cvss4": {"value": 8.0, "source": "synthetic-cvss"},
        "epss": {"value": 0.6, "source": "synthetic-epss"},
        "kev": {"value": True, "source": "synthetic-kev"},
        "asset_criticality": {"value": 0.9, "source": "synthetic-asset"},
        "reachability": {"value": 0.8, "source": "synthetic-topology"},
        "attack_path_importance": {"value": 0.7, "source": "synthetic-graph"},
        "threat_relevance": {"value": 0.8, "source": "synthetic-threat-profile"},
        "compensating_controls": {"value": 0.3, "source": "synthetic-control-assessment"},
        "detectability": {"value": 0.5, "source": "synthetic-purple-team"},
        "remediation_cost": {"value": 0.4, "source": "synthetic-remediation-estimate"},
    }


def _risk():
    return build_risk_assessment(components=_components(), weights={name: 0.1 for name in _components()})


def _finding():
    return create_finding(
        title="Synthetic validation finding",
        risk=_risk(),
        root_cause="synthetic unsafe data path",
        systemic=True,
        evidence_before=["evidence-before-1"],
    )


def test_risk_components_remain_separate_sourced_and_auditable() -> None:
    risk = _risk()
    assert risk["auditable"] is True
    assert set(risk["components"]) == set(_components())
    assert all(item["source"] for item in risk["components"].values())
    assert sum(risk["weights"].values()) == pytest.approx(1.0)
    assert 0 <= risk["composite_score"] <= 1


def test_invalid_weights_and_missing_sources_fail_closed() -> None:
    with pytest.raises(RiskFindingError):
        build_risk_assessment(components=_components(), weights={name: 0.2 for name in _components()})
    broken = _components()
    broken["epss"] = {"value": 0.6, "source": ""}
    with pytest.raises(RiskFindingError):
        build_risk_assessment(components=broken, weights={name: 0.1 for name in broken})


def test_finding_starts_observed_with_before_evidence_and_schema_validates() -> None:
    finding = _finding()
    assert finding["state"] == "OBSERVED"
    assert finding["evidence_before"] == ["evidence-before-1"]
    assert finding["systemic"] is True
    schema = json.loads((RISK_DIR / "finding.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(finding)


def test_lifecycle_is_explicit_and_skips_are_blocked() -> None:
    finding = _finding()
    with pytest.raises(RiskFindingError):
        transition(finding, target="CLOSED", actor="synthetic-reviewer")
    finding = transition(finding, target="VALIDATED", actor="synthetic-reviewer")
    finding = transition(finding, target="TRIAGED", actor="synthetic-reviewer")
    finding = transition(finding, target="ASSIGNED", actor="synthetic-owner")
    finding = transition(finding, target="FIXED", actor="synthetic-owner")
    finding = transition(finding, target="RETEST", actor="synthetic-reviewer", evidence_after=["evidence-after-1"], remediation_effectiveness=0.9)
    finding = transition(finding, target="VERIFIED", actor="synthetic-reviewer", evidence_after=["evidence-after-1"])
    finding = transition(finding, target="CLOSED", actor="synthetic-reviewer", evidence_after=["evidence-after-1"])
    assert finding["state"] == "CLOSED"
    assert finding["remediation_effectiveness"] == 0.9


def test_regression_reopens_with_comparable_evidence() -> None:
    finding = _finding()
    finding = transition(finding, target="VALIDATED", actor="reviewer")
    finding = transition(finding, target="TRIAGED", actor="reviewer")
    finding = transition(finding, target="ASSIGNED", actor="owner")
    finding = transition(finding, target="FIXED", actor="owner")
    finding = transition(finding, target="RETEST", actor="reviewer", evidence_after=["evidence-after-fixed"])
    finding = transition(finding, target="VERIFIED", actor="reviewer", evidence_after=["evidence-after-fixed"])
    regressed = record_regression(finding, actor="reviewer", evidence_after=["evidence-after-regression"])
    assert regressed["state"] == "REGRESSED"
    assert regressed["reopened"] is True
    assert regressed["evidence_before"]
    assert regressed["evidence_after"] == ["evidence-after-regression"]


def test_regression_without_prior_assessment_is_blocked() -> None:
    with pytest.raises(RiskFindingError):
        record_regression(_finding(), actor="reviewer", evidence_after=["evidence-after"])


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((RISK_DIR / "risk-policy.yaml").read_text())
    assert policy["risk"]["source_required_per_component"] is True
    assert policy["findings"]["regression_reopens"] is True
    assert policy["runtime_status"] == {
        "cvss_feed": "NOT_IMPLEMENTED",
        "epss_feed": "NOT_IMPLEMENTED",
        "kev_feed": "NOT_IMPLEMENTED",
        "ticketing_integration": "NOT_IMPLEMENTED",
        "automatic_risk_acceptance": "NOT_RUN",
        "remediation_execution": "NOT_RUN",
    }
