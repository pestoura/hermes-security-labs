from __future__ import annotations

import copy
import ipaddress
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "deployment" / "shared-vault-hsl"
SCHEMA = DIR / "secret-zero-reconciliation.schema.json"
TEMPLATE = DIR / "secret-zero-reconciliation.yaml"
CHANGE = ROOT / "changes" / "CHG-HSL-100.yaml"
OBSERVATION_CHANGE = ROOT / "changes" / "CHG-HSL-103.yaml"


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _template() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def _observed_pass() -> dict:
    doc = _template()
    doc["state"] = "OBSERVED_PASS"
    doc["observed_at"] = "2026-08-27T19:31:00Z"
    doc["operator_result"] = {
        "issuance_completed": True,
        "wrapped_delivery_created": True,
        "unwrap_consumed_once": True,
        "login_succeeded": True,
        "positive_capability_probe_passed": True,
        "negative_capability_checks_passed": True,
        "no_secret_material_persisted": True,
    }
    return doc


def test_chg100_artifacts_exist() -> None:
    for path in (SCHEMA, TEMPLATE, CHANGE):
        assert path.exists(), f"missing CHG-HSL-100 artifact: {path.relative_to(ROOT)}"


def test_committed_reconciliation_is_observed_pass_and_non_authoritative() -> None:
    schema = _schema()
    doc = _template()
    jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).validate(doc)
    assert schema["additionalProperties"] is False
    assert doc["schema_version"] == "hsl.shared-vault-secret-zero-reconciliation/v1"
    assert doc["issue"] == 439
    assert doc["change_record"] == "CHG-HSL-100"
    assert doc["provider"] == "hermes-shared-vault"
    assert doc["state"] == "OBSERVED_PASS"
    assert doc["observed_at"] == "2026-08-29T20:06:54Z"
    assert doc["operator_result"] == {
        "issuance_completed": True,
        "wrapped_delivery_created": True,
        "unwrap_consumed_once": True,
        "login_succeeded": True,
        "positive_capability_probe_passed": True,
        "negative_capability_checks_passed": True,
        "no_secret_material_persisted": True,
    }
    cidr = ipaddress.ip_network(doc["consumer_cidr"], strict=True)
    assert cidr.version == 4 and cidr.prefixlen == 32
    assert doc["policy_metadata"]["credential_bound_cidr"] == doc["consumer_cidr"]
    assert doc["policy_metadata"]["token_bound_cidr"] == doc["consumer_cidr"]
    assert doc["authority"]["trust_binding_allowed"] is False
    assert doc["authority"]["supplier_selection_effect"] == "NONE"
    assert doc["authority"]["signer_decision_effect"] == "NONE"
    assert doc["authority"]["promotion_allowed"] is False
    assert doc["authority"]["execution_authority"] == "NONE"
    assert doc["authority"]["runner_effect"] is False
    assert doc["authority"]["target_effect"] is False
    assert all(value is False for value in doc["sanitization"].values())


def test_observed_pass_requires_every_operator_fact_true() -> None:
    validator = jsonschema.Draft7Validator(_schema(), format_checker=jsonschema.FormatChecker())
    passing = _observed_pass()
    validator.validate(passing)
    for key in list(passing["operator_result"]):
        candidate = copy.deepcopy(passing)
        candidate["operator_result"][key] = False
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(candidate)


def test_observed_fail_is_recordable_but_cannot_grant_authority() -> None:
    validator = jsonschema.Draft7Validator(_schema(), format_checker=jsonschema.FormatChecker())
    failed = _observed_pass()
    failed["state"] = "OBSERVED_FAIL"
    failed["operator_result"]["login_succeeded"] = False
    validator.validate(failed)
    unsafe_mutations = (
        ("trust_binding_allowed", True),
        ("promotion_allowed", True),
        ("runner_effect", True),
        ("target_effect", True),
        ("execution_authority", "RUNNER"),
    )
    for key, value in unsafe_mutations:
        candidate = copy.deepcopy(failed)
        candidate["authority"][key] = value
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(candidate)


def test_sensitive_fields_are_rejected_by_closed_contract() -> None:
    validator = jsonschema.Draft7Validator(_schema(), format_checker=jsonschema.FormatChecker())
    base = _observed_pass()
    cases = (
        (None, "credential_value"),
        ("operator_result", "secret_value"),
        ("policy_metadata", "credential_material"),
        ("sanitization", "raw_secret"),
        ("authority", "token_value"),
    )
    for container_name, forbidden_key in cases:
        candidate = copy.deepcopy(base)
        target = candidate if container_name is None else candidate[container_name]
        target[forbidden_key] = "FORBIDDEN"
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(candidate)


def test_chg103_records_observation_without_granting_authority() -> None:
    assert OBSERVATION_CHANGE.exists(), "missing CHG-HSL-103 observation record"
    record = yaml.safe_load(OBSERVATION_CHANGE.read_text(encoding="utf-8"))
    assert record["id"] == "CHG-HSL-103"
    assert record["issue"] == 439
    assert record["classification"] == "DOC_ONLY"
    assert record["validation"]["runtime"] == "PASS"
    assert len(record["source"]["reference"]) <= 500
    assert record["promotion"]["commit"] is None
    text = OBSERVATION_CHANGE.read_text(encoding="utf-8")
    for marker in (
        "OBSERVED_PASS",
        "NO_DECISION",
        "NO_SELECTION",
        "trust_binding_allowed=false",
        "promotion_allowed=false",
        "execution_authority=NONE",
    ):
        assert marker in text


def test_change_record_preserves_hitl_and_not_run_runtime() -> None:
    record = yaml.safe_load(CHANGE.read_text(encoding="utf-8"))
    assert record["id"] == "CHG-HSL-100"
    assert record["issue"] == 439
    assert record["validation"]["runtime"] == "NOT_RUN"
    assert record["promotion"]["commit"] is None
    text = CHANGE.read_text(encoding="utf-8")
    for marker in (
        "operator-only HITL",
        "NO_DECISION",
        "NO_SELECTION",
        "promotion_allowed=false",
        "execution_authority=NONE",
    ):
        assert marker in text
