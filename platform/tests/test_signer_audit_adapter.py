#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
MODULE_PATH = ASSURANCE / "signer_audit_adapter.py"
SIGNING_PATH = ASSURANCE / "signing_service.py"
TEST_SIGNER_PATH = ASSURANCE / "test_signer_adapter.py"


def _load(path: Path, name: str):
    assert path.exists(), f"{path.name} is not implemented yet"
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signing():
    return _load(SIGNING_PATH, "chg_hsl_075_signing_service")


def _adapter():
    return _load(MODULE_PATH, "chg_hsl_075_signer_audit_adapter")


def _request():
    signing = _signing()
    return signing.SigningRequest(
        digest_sha256="a" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-001",
    )


def _external_result():
    signing = _signing()
    return signing.SigningResult(
        signature_b64="YQ==",
        key_id="key-001",
        algorithm="Ed25519",
        public_key_spki_sha256="b" * 64,
        signer_class="VAULT",
        authority="EXTERNAL_CUSTODY",
        admissible_for_lab_l1=True,
        audit_ref="evidence://signer/audit-001",
    )


def _attribution(*, test_only: bool = False):
    adapter = _adapter()
    return adapter.SignerAuditAttribution(
        principal="hermes-assurance",
        provider_ref="provider-ref-001",
        test_only=test_only,
    )


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-001",
        "run_id": "run-001",
        "step_id": "sign-001",
        "attempt_id": "attempt-001",
    }


def test_build_record_is_public_deterministic_and_content_addressable() -> None:
    adapter = _adapter()
    request = _request()
    result = _external_result()
    record = adapter.build_signer_audit_record(request, result, _attribution())

    assert record["schema_version"] == "signer-operation-audit/v1"
    assert record["operation"] == "SIGN"
    assert record["request_digest_sha256"] == request.digest_sha256
    assert record["signature_sha256"] == adapter.sha256_hex(b"a")
    assert record["principal"] == "hermes-assurance"
    assert record["provider_ref"] == "provider-ref-001"
    assert record["test_only"] is False
    assert record["promotion_allowed"] is False
    assert record["runtime_status"] == "NOT_RUN"
    assert record["execution_authority"] == "NONE"
    assert "signature_b64" not in record
    assert "payload" not in record
    assert "private_key" not in record
    assert "secret" not in record
    assert "token" not in record
    assert "credential" not in record

    digest1, size1 = adapter.signer_record_digest(record)
    digest2, size2 = adapter.signer_record_digest(dict(reversed(list(record.items()))))
    assert digest1 == digest2
    assert size1 == size2
    assert len(digest1) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("principal", ""),
        ("principal", "principal\nroot"),
        ("provider_ref", ""),
        ("provider_ref", "provider\x00ref"),
    ],
)
def test_attribution_fails_closed_on_missing_or_unsafe_values(field: str, value: str) -> None:
    adapter = _adapter()
    attribution = replace(_attribution(), **{field: value})
    with pytest.raises(adapter.SignerAuditError) as exc:
        adapter.build_signer_audit_record(_request(), _external_result(), attribution)
    assert exc.value.code == "SIGNER_AUDIT_ATTRIBUTION_INVALID"


def test_invalid_request_is_rejected_by_canonical_signing_contract() -> None:
    adapter = _adapter()
    request = replace(_request(), purpose="arbitrary")
    with pytest.raises(adapter.SignerAuditError) as exc:
        adapter.build_signer_audit_record(request, _external_result(), _attribution())
    assert exc.value.code == "SIGNER_AUDIT_REQUEST_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("signature_b64", "not-base64!"),
        ("key_id", ""),
        ("algorithm", "RSA"),
        ("public_key_spki_sha256", "B" * 64),
        ("signer_class", "PKCS11"),
        ("audit_ref", "file:///tmp/audit"),
    ],
)
def test_public_result_metadata_is_validated_fail_closed(field: str, value: object) -> None:
    adapter = _adapter()
    result = replace(_external_result(), **{field: value})
    with pytest.raises(adapter.SignerAuditError) as exc:
        adapter.build_signer_audit_record(_request(), result, _attribution())
    assert exc.value.code == "SIGNER_AUDIT_RESULT_INVALID"


def test_ci_test_signer_is_explicitly_test_only_and_never_promotion_evidence() -> None:
    adapter = _adapter()
    test_signer = _load(TEST_SIGNER_PATH, "chg_hsl_075_test_signer")
    result = test_signer.TestSignerAdapter(b"\x66" * 32).sign(_request())
    record = adapter.build_signer_audit_record(
        _request(), result, _attribution(test_only=True)
    )
    assert record["signer_class"] == "TEST"
    assert record["test_only"] is True
    assert record["promotion_allowed"] is False
    assert record["runtime_status"] == "NOT_RUN"
    assert record["execution_authority"] == "NONE"

    with pytest.raises(adapter.SignerAuditError) as exc:
        adapter.build_signer_audit_record(
            _request(), result, _attribution(test_only=False)
        )
    assert exc.value.code == "SIGNER_AUDIT_TEST_CLASSIFICATION_REQUIRED"


def test_adapter_appends_exactly_one_record_to_existing_canonical_audit_sink() -> None:
    adapter = _adapter()
    sink = adapter.CanonicalSignerAuditAdapter(
        chain_id="chain_" + "d" * 32,
        correlation=_correlation(),
    )
    record = sink.record_signing(
        request=_request(), result=_external_result(), attribution=_attribution()
    )
    assert sink.length == 1
    document = sink.seal(sealed_at="2026-08-16T00:00:00Z")
    assert len(document["entries"]) == 1
    digest, size = adapter.signer_record_digest(record)
    entry = document["entries"][0]
    assert entry["object_kind"] == "evidence_record"
    assert entry["object_digest_sha256"] == digest
    assert entry["object_size_bytes"] == size
    assert entry["object_ref"] == f"evidence://signer-operation/{digest}"
    assert entry["audit"]["principal"] == "hermes-assurance"
    assert entry["audit"]["decision"] == "SIGN"
    assert entry["audit"]["correlation_id"] == "corr-001"
    assert sink.verify()["verified"] is True


def test_identical_signer_audit_event_replay_fails_closed() -> None:
    adapter = _adapter()
    sink = adapter.CanonicalSignerAuditAdapter(
        chain_id="chain_" + "e" * 32,
        correlation=_correlation(),
    )
    kwargs = {
        "request": _request(),
        "result": _external_result(),
        "attribution": _attribution(),
    }
    sink.record_signing(**kwargs)
    with pytest.raises(adapter.SignerAuditError) as exc:
        sink.record_signing(**kwargs)
    assert exc.value.code == "SIGNER_AUDIT_APPEND_FAILED"


def test_adapter_has_no_provider_runtime_or_second_ledger_dependencies() -> None:
    _adapter()
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_roots = {
        "boto3",
        "hvac",
        "pkcs11",
        "requests",
        "httpx",
        "socket",
        "subprocess",
    }
    imported: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
    assert imported.isdisjoint(forbidden_roots)
    assert "EvidenceChain" not in called_names
    assert "seal_chain" not in called_names
