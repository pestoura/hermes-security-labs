from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"

spec = importlib.util.spec_from_file_location("evidence_plane", EVIDENCE_DIR / "evidence_plane.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

Correlation = module.Correlation
EvidenceError = module.EvidenceError
build_record = module.build_record
exportable = module.exportable
replay_descriptor = module.replay_descriptor
sha256_hex = module.sha256_hex
verify_chain = module.verify_chain


def _base_record(classification: str = "raw", **overrides):
    payload = b"synthetic evidence payload"
    kwargs = {
        "correlation": Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        "classification": classification,
        "producer": "synthetic-runner",
        "operation": "conformance.process.success",
        "protocol_version": "2.0",
        "payload_sha256": sha256_hex(payload),
        "payload_size": len(payload),
        "media_type": "application/json",
        "storage_ref": "evidence://campaign-1/run-1/raw/result.json",
        "retention_policy_id": "default-30d",
        "retain_until": "2026-09-06T00:00:00Z",
        "created_at": "2026-08-07T00:00:00Z",
    }
    kwargs.update(overrides)
    return build_record(**kwargs)


def test_schema_accepts_canonical_raw_record() -> None:
    schema = json.loads((EVIDENCE_DIR / "evidence-record.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(_base_record())


def test_all_four_correlation_ids_are_mandatory_and_bounded() -> None:
    record = _base_record()
    assert set(record["correlation"]) == {"campaign_id", "run_id", "step_id", "attempt_id"}
    with pytest.raises(EvidenceError):
        _base_record(correlation=Correlation("campaign-1", "run-1", "step-1", "bad id with spaces"))


def test_raw_evidence_is_not_exportable_by_default() -> None:
    assert exportable(_base_record("raw")) is False
    assert exportable(_base_record("restricted")) is False


def test_sanitized_evidence_requires_parent_and_redaction_lineage() -> None:
    raw = _base_record("raw")
    with pytest.raises(EvidenceError):
        _base_record("sanitized")
    sanitized_payload = b"sanitized synthetic result"
    sanitized = _base_record(
        "sanitized",
        payload_sha256=sha256_hex(sanitized_payload),
        payload_size=len(sanitized_payload),
        storage_ref="evidence://campaign-1/run-1/sanitized/result.json",
        parent_evidence_id=raw["evidence_id"],
        redaction={
            "policy_id": "contextual-v1",
            "source_sha256": raw["content"]["sha256"],
            "removed_classes": ["secret", "raw_output"],
        },
    )
    assert exportable(sanitized) is True
    assert verify_chain([raw, sanitized]) is True


def test_chain_fails_closed_on_parent_digest_mismatch() -> None:
    raw = _base_record("raw")
    sanitized = _base_record(
        "sanitized",
        parent_evidence_id=raw["evidence_id"],
        redaction={
            "policy_id": "contextual-v1",
            "source_sha256": "0" * 64,
            "removed_classes": ["raw_output"],
        },
    )
    assert verify_chain([raw, sanitized]) is False


@pytest.mark.parametrize("forbidden", ["token", "password", "authorization", "stdout", "stderr", "command", "argv"])
def test_secret_or_raw_output_metadata_is_refused(forbidden: str) -> None:
    with pytest.raises(EvidenceError):
        _base_record(metadata={forbidden: "synthetic-canary"})


def test_replay_descriptor_contains_no_payload_or_storage_reference() -> None:
    descriptor = replay_descriptor(_base_record())
    serialized = json.dumps(descriptor)
    assert "storage_ref" not in descriptor
    assert "payload" not in descriptor
    assert "evidence://" not in serialized
    assert set(descriptor) == {
        "schema_version", "evidence_id", "correlation", "producer", "operation",
        "protocol_version", "knowledge_snapshot", "payload_sha256",
    }


def test_policy_records_local_controlled_persistence_without_production_overclaim() -> None:
    policy = yaml.safe_load((EVIDENCE_DIR / "evidence-policy.yaml").read_text())
    assert policy["sharing_default"] == "deny"
    assert policy["classifications"]["raw"]["shareable"] is False
    assert policy["classifications"]["restricted"]["shareable"] is False
    assert policy["runtime_status"] == {
        "storage_backend": "PASS_LOCAL_CONTROLLED_CI",
        "local_integrity_replay": "PASS_CONTROLLED_CI",
        "local_export_boundary": "PASS_CONTROLLED_CI",
        "encryption_at_rest": "NOT_RUN",
        "immutable_store": "NOT_RUN",
        "retention_enforcement": "NOT_RUN",
        "production_replay": "NOT_RUN",
        "production_redaction": "NOT_RUN",
        "customer_export": "NOT_RUN",
    }
    assert policy["runtime_evidence"] == {
        "boundary": "local_controlled_ci",
        "technical_pr": 217,
        "merge_sha": "aa589bbaa6ede9192963ff2a47244ab34309c1c6",
        "backend": "local_content_addressed_filesystem",
        "object_storage": "NOT_RUN",
        "worm_storage": "NOT_RUN",
        "deployed_runtime": "NOT_RUN",
    }


def test_repository_owns_all_contract_files() -> None:
    expected = {
        "README.md",
        "evidence-record.schema.json",
        "evidence-policy.yaml",
        "evidence_plane.py",
        "local_store.py",
    }
    assert expected.issubset({path.name for path in EVIDENCE_DIR.iterdir()})
    for name in expected:
        assert (EVIDENCE_DIR / name).resolve().is_relative_to(ROOT.resolve())
