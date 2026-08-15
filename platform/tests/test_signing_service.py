#!/usr/bin/env python3
"""CHG-HSL-073 tests for the provider-neutral signing-service boundary.

The first TDD commit intentionally lands before the production module. Tests load the
module dynamically so the RED state is an assertion failure that the contract is absent,
not an import-time collection error.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "assurance" / "signing_service.py"


def _load_module():
    assert MODULE_PATH.exists(), "provider-neutral signing_service.py is not implemented yet"
    spec = importlib.util.spec_from_file_location("signing_service_test", MODULE_PATH)
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
    result = module.SigningResult(
        signature_b64="YQ==",
        key_id="key-1",
        algorithm="Ed25519",
        public_key_spki_sha256="b" * 64,
        signer_class="VAULT",
        authority="EXTERNAL_CUSTODY",
        admissible_for_lab_l1=True,
        audit_ref="evidence://signer/audit-1",
    )
    assert result.key_id == "key-1"
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
