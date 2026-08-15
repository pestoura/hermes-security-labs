#!/usr/bin/env python3
"""CHG-HSL-073 tests for the provider-neutral signing-service boundary.

Tests intentionally drive the contract through TDD. Dynamic loading keeps this
repository-only assurance directory independent from Python package layout decisions.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"
MODULE_PATH = ASSURANCE_DIR / "signing_service.py"
ADAPTER_PATH = ASSURANCE_DIR / "test_signer_adapter.py"


def _load_module():
    assert MODULE_PATH.exists(), "provider-neutral signing_service.py is not implemented yet"
    spec = importlib.util.spec_from_file_location("signing_service_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    assert ADAPTER_PATH.exists(), "CI-only test_signer_adapter.py is not implemented yet"
    spec = importlib.util.spec_from_file_location("signer_adapter_guard_test", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_request(module):
    return module.SigningRequest(
        digest_sha256="a" * 64,
        purpose="tb1-authorization-receipt",
        domain="hermes-security-labs/lab-l1",
        correlation_id="corr-001",
    )


def _valid_external_result(module):
    return module.SigningResult(
        signature_b64="YQ==",
        key_id="vault-key-1",
        algorithm="Ed25519",
        public_key_spki_sha256="b" * 64,
        signer_class="VAULT",
        authority="EXTERNAL_CUSTODY",
        admissible_for_lab_l1=True,
        audit_ref="evidence://signer/audit-1",
    )


def test_valid_request_is_accepted_unchanged() -> None:
    module = _load_module()
    request = _valid_request(module)
    assert module.validate_signing_request(request) is request


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("digest_sha256", "A" * 64),
        ("digest_sha256", "a" * 63),
        ("digest_sha256", "g" * 64),
        ("purpose", ""),
        ("purpose", "p" * 129),
        ("purpose", "tb1\nreceipt"),
        ("domain", ""),
        ("domain", "d" * 257),
        ("domain", "lab\rprod"),
        ("correlation_id", ""),
        ("correlation_id", "c" * 129),
        ("correlation_id", "corr\x00bad"),
    ],
)
def test_invalid_signing_request_fails_closed(field: str, value: str) -> None:
    module = _load_module()
    request = replace(_valid_request(module), **{field: value})
    with pytest.raises(module.SigningServiceError) as exc:
        module.validate_signing_request(request)
    assert exc.value.code == "SIGNING_REQUEST_INVALID"


def test_signing_result_contains_only_public_boundary_metadata() -> None:
    module = _load_module()
    result = _valid_external_result(module)
    assert result.key_id == "vault-key-1"
    assert not hasattr(result, "private_key")
    assert not hasattr(result, "secret")
    assert not hasattr(result, "token")
    assert not hasattr(result, "credential")


def test_contract_imports_no_runtime_or_provider_clients() -> None:
    _load_module()
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden_roots)


def test_signing_service_protocol_exposes_only_sign() -> None:
    module = _load_module()
    public_methods = {
        name
        for name, value in vars(module.SigningService).items()
        if callable(value) and not name.startswith("_")
    }
    assert public_methods == {"sign"}


def test_lab_l1_guard_rejects_ci_only_signer_result() -> None:
    module = _load_module()
    adapter_module = _load_adapter()
    ci_result = adapter_module.TestSignerAdapter(b"\x66" * 32).sign(_valid_request(module))
    with pytest.raises(module.SigningServiceError) as exc:
        module.require_lab_l1_admissible(ci_result)
    assert exc.value.code == "SIGNER_NOT_ADMISSIBLE"


def test_lab_l1_guard_accepts_structurally_valid_external_custody_envelope_only() -> None:
    module = _load_module()
    result = _valid_external_result(module)
    assert module.require_lab_l1_admissible(result) is result


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("admissible_for_lab_l1", False, "SIGNER_NOT_ADMISSIBLE"),
        ("signer_class", "TEST", "SIGNER_NOT_ADMISSIBLE"),
        ("signer_class", "PKCS11", "SIGNER_NOT_ADMISSIBLE"),
        ("authority", "CI_ONLY/NON_AUTHORITATIVE", "SIGNER_NOT_ADMISSIBLE"),
        ("algorithm", "RSA", "SIGNER_RESPONSE_INVALID"),
        ("key_id", "", "SIGNER_RESPONSE_INVALID"),
        ("public_key_spki_sha256", "B" * 64, "SIGNER_RESPONSE_INVALID"),
        ("signature_b64", "not base64!", "SIGNER_RESPONSE_INVALID"),
        ("audit_ref", "", "SIGNER_RESPONSE_INVALID"),
        ("audit_ref", "ci-test://corr/aaaa", "SIGNER_RESPONSE_INVALID"),
    ],
)
def test_lab_l1_guard_fails_closed_on_inadmissible_or_malformed_results(
    field: str, value: object, expected_code: str
) -> None:
    module = _load_module()
    result = replace(_valid_external_result(module), **{field: value})
    with pytest.raises(module.SigningServiceError) as exc:
        module.require_lab_l1_admissible(result)
    assert exc.value.code == expected_code
