from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "platform" / "runner-authorization" / "authorization_audit_adapter.py"
SCHEMA_PATH = ROOT / "platform" / "schemas" / "authorization-receipt-audit.schema.json"


def _load(path: Path, name: str) -> Any:
    assert path.exists(), f"{path.name} is not implemented yet"
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _adapter():
    return _load(ADAPTER_PATH, "chg_hsl_078_authorization_audit")


def _schema() -> dict[str, Any]:
    assert SCHEMA_PATH.exists(), "authorization receipt audit schema is not implemented yet"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _context():
    module = _adapter()
    return module.AuthorizationAuditContext(
        campaign_id="campaign-078",
        run_id="run-078",
        step_id="step-078",
        attempt_id="attempt-078",
        principal="hexor.runner",
        correlation_id="corr-078",
    )


def _canonical_ref() -> str:
    return "tb1-authz:v1:" + "a" * 64


def _record(**overrides: Any) -> dict[str, Any]:
    module = _adapter()
    values = {
        "event_type": "REGISTERED",
        "phase": "REGISTRATION",
        "decision": "ACCEPT",
        "reason_code": "RECEIPT_VERIFIED",
        "authorization_ref": _canonical_ref(),
        "duplicate": False,
        "capability_id": "web.discovery.headers",
        "intrusiveness_level": "L1",
    }
    values.update(overrides)
    return module.build_authorization_audit_record(**values)


def test_schema_is_closed_and_locks_authority_fields() -> None:
    schema = _schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    required = set(schema["required"])
    assert required == {
        "schema_version",
        "event_type",
        "phase",
        "decision",
        "reason_code",
        "authorization_ref_sha256",
        "duplicate",
        "capability_id",
        "intrusiveness_level",
        "promotion_allowed",
        "runtime_status",
        "execution_authority",
    }
    props = schema["properties"]
    assert props["promotion_allowed"]["const"] is False
    assert props["runtime_status"]["const"] == "NOT_RUN"
    assert props["execution_authority"]["const"] == "NONE"


@pytest.mark.parametrize(
    "event_type,phase,decision,reason_code",
    [
        ("REGISTERED", "REGISTRATION", "ACCEPT", "RECEIPT_VERIFIED"),
        ("LOOKUP_HIT", "LOOKUP", "ACCEPT", "AUTHORIZATION_LIVE"),
        ("LOOKUP_MISS", "LOOKUP", "DENY", "AUTHORIZATION_NOT_FOUND"),
        ("LOOKUP_EXPIRED", "LOOKUP", "DENY", "AUTHORIZATION_NOT_LIVE"),
        ("REFUSED", "DELIVERY", "DENY", "PEER_UID_UNAUTHORIZED"),
        ("REFUSED", "REGISTRATION", "DENY", "TB1_AUTH_SIGNATURE_INVALID"),
    ],
)
def test_valid_event_matrix_passes_schema_and_contract(
    event_type: str, phase: str, decision: str, reason_code: str
) -> None:
    record = _record(
        event_type=event_type,
        phase=phase,
        decision=decision,
        reason_code=reason_code,
        capability_id=None if decision == "DENY" else "web.discovery.headers",
        intrusiveness_level=None if decision == "DENY" else "L1",
    )
    jsonschema.Draft202012Validator(_schema()).validate(record)


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_type": "REGISTERED", "phase": "LOOKUP", "decision": "ACCEPT"},
        {"event_type": "LOOKUP_HIT", "phase": "REGISTRATION", "decision": "ACCEPT"},
        {"event_type": "LOOKUP_MISS", "phase": "LOOKUP", "decision": "ACCEPT"},
        {"event_type": "LOOKUP_EXPIRED", "phase": "LOOKUP", "decision": "ACCEPT"},
        {"event_type": "REFUSED", "phase": "DELIVERY", "decision": "ACCEPT"},
    ],
)
def test_invalid_event_phase_decision_combinations_fail_closed(overrides: dict[str, str]) -> None:
    module = _adapter()
    with pytest.raises(module.AuthorizationAuditError):
        _record(**overrides)


def test_canonical_authorization_reference_is_persisted_only_as_sha256() -> None:
    ref = _canonical_ref()
    record = _record(authorization_ref=ref)
    assert record["authorization_ref_sha256"] == hashlib.sha256(ref.encode("utf-8")).hexdigest()
    serialized = json.dumps(record, sort_keys=True)
    assert ref not in serialized
    assert "tb1-authz:v1:" not in serialized


@pytest.mark.parametrize(
    "value",
    [None, "", "garbage", "tb1-authz:v1:NOTHEX", "x" * 1024],
)
def test_noncanonical_or_unbounded_authorization_reference_is_never_persisted(value: Any) -> None:
    record = _record(
        event_type="LOOKUP_MISS",
        phase="LOOKUP",
        decision="DENY",
        reason_code="AUTHORIZATION_REF_INVALID",
        authorization_ref=value,
        capability_id=None,
        intrusiveness_level=None,
    )
    assert record["authorization_ref_sha256"] is None
    serialized = json.dumps(record, sort_keys=True)
    if isinstance(value, str) and value:
        assert value not in serialized


@pytest.mark.parametrize(
    "reason_code",
    ["", "contains space", "../escape", "x" * 257, "bad\ncode"],
)
def test_reason_code_must_be_bounded_safe_machine_label(reason_code: str) -> None:
    module = _adapter()
    with pytest.raises(module.AuthorizationAuditError):
        _record(reason_code=reason_code)


def test_verified_metadata_fields_are_bounded_and_optional_on_denial() -> None:
    module = _adapter()
    denied = _record(
        event_type="LOOKUP_MISS",
        phase="LOOKUP",
        decision="DENY",
        reason_code="AUTHORIZATION_NOT_FOUND",
        capability_id=None,
        intrusiveness_level=None,
    )
    assert denied["capability_id"] is None
    assert denied["intrusiveness_level"] is None

    with pytest.raises(module.AuthorizationAuditError):
        _record(capability_id="x" * 300)
    with pytest.raises(module.AuthorizationAuditError):
        _record(intrusiveness_level="L1\nsecret")


def test_record_is_deterministic_and_content_addressable() -> None:
    module = _adapter()
    first = _record()
    second = _record()
    assert second == first
    first_digest, first_size = module.authorization_audit_record_digest(first)
    second_digest, second_size = module.authorization_audit_record_digest(second)
    assert first_digest == second_digest
    assert first_size == second_size
    canonical = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    assert first_digest == hashlib.sha256(canonical).hexdigest()
    assert first_size == len(canonical)


def test_public_record_contains_no_sensitive_or_authority_expanding_material() -> None:
    record = _record()
    assert record["promotion_allowed"] is False
    assert record["runtime_status"] == "NOT_RUN"
    assert record["execution_authority"] == "NONE"
    forbidden_keys = {
        "receipt",
        "signature",
        "signature_b64",
        "private_key",
        "public_key",
        "secret",
        "token",
        "cookie",
        "credential",
        "target",
        "target_sha256",
        "parameters",
        "operation_parameters",
        "authorization_ref",
    }
    assert forbidden_keys.isdisjoint(record)
    serialized = json.dumps(record, sort_keys=True)
    assert _canonical_ref() not in serialized
    assert "tb1-authz:v1:" not in serialized


def test_adapter_appends_to_existing_canonical_audit_sink_only() -> None:
    module = _adapter()
    adapter = module.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "7" * 32,
    )
    record = adapter.record_event(
        context=_context(),
        event_type="REGISTERED",
        phase="REGISTRATION",
        decision="ACCEPT",
        reason_code="RECEIPT_VERIFIED",
        authorization_ref=_canonical_ref(),
        duplicate=False,
        capability_id="web.discovery.headers",
        intrusiveness_level="L1",
    )
    assert adapter.length == 1
    digest, size = module.authorization_audit_record_digest(record)
    document = adapter.seal(sealed_at="2026-08-16T03:30:00Z")
    entry = document["entries"][0]
    assert entry["object_ref"] == f"evidence://authorization-receipt-audit/{digest}"
    assert entry["object_digest_sha256"] == digest
    assert entry["object_size_bytes"] == size
    assert entry["object_media_type"] == "application/json"
    assert entry["audit"]["campaign_id"] == "campaign-078"
    assert entry["audit"]["run_id"] == "run-078"
    assert entry["audit"]["step_id"] == "step-078"
    assert entry["audit"]["attempt_id"] == "attempt-078"
    assert entry["audit"]["principal"] == "hexor.runner"
    assert entry["audit"]["correlation_id"] == "corr-078"
    assert entry["audit"]["outcome"] == "recorded"


def test_denial_maps_to_canonical_denied_audit_outcome() -> None:
    module = _adapter()
    adapter = module.CanonicalAuthorizationAuditAdapter(chain_id="chain_" + "8" * 32)
    adapter.record_event(
        context=_context(),
        event_type="LOOKUP_MISS",
        phase="LOOKUP",
        decision="DENY",
        reason_code="AUTHORIZATION_NOT_FOUND",
        authorization_ref=_canonical_ref(),
        duplicate=False,
        capability_id=None,
        intrusiveness_level=None,
    )
    document = adapter.seal(sealed_at="2026-08-16T03:31:00Z")
    assert document["entries"][0]["audit"]["outcome"] == "denied"


def test_audit_context_is_closed_and_rejects_unsafe_values() -> None:
    module = _adapter()
    with pytest.raises((TypeError, module.AuthorizationAuditError, ValueError)):
        module.AuthorizationAuditContext(
            campaign_id="campaign-078",
            run_id="run-078",
            step_id="step-078",
            attempt_id="attempt-078",
            principal="bad principal with spaces",
            correlation_id="corr-078",
        )


def test_source_introduces_no_runtime_provider_or_parallel_integrity_primitive() -> None:
    _adapter()
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    defined_classes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            defined_classes.add(node.name)
    assert not imported & {
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "boto3",
        "hvac",
        "pkcs11",
        "docker",
    }
    assert "EvidenceChain" not in defined_classes
    assert "AuditSink" not in defined_classes
    assert "LocalEvidenceStore" not in defined_classes
    assert "LocalEvidenceVerifier" not in defined_classes
    assert "seal_chain" not in source
    assert "AuditSink(" in source
