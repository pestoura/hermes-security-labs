#!/usr/bin/env python3
"""CHG-HSL-073 TDD tests for the CI-only non-authoritative signer adapter."""

from __future__ import annotations

import ast
import base64
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"
SIGNING_SERVICE_PATH = ASSURANCE_DIR / "signing_service.py"
ADAPTER_PATH = ASSURANCE_DIR / "test_signer_adapter.py"


def _load(path: Path, name: str):
    assert path.exists(), f"{path.name} is not implemented yet"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _modules():
    signing = _load(SIGNING_SERVICE_PATH, "chg_hsl_073_signing_service_test")
    adapter = _load(ADAPTER_PATH, "chg_hsl_073_test_signer_adapter")
    return signing, adapter


def _request(signing):
    return signing.SigningRequest(
        digest_sha256="a" * 64,
        purpose="tb1-authorization-receipt",
        domain="hermes-security-labs/lab-l1",
        correlation_id="corr-001",
    )


def test_ci_signer_is_deterministic_for_same_request_and_seed() -> None:
    signing, adapter_module = _modules()
    signer = adapter_module.TestSignerAdapter(b"\x11" * 32)
    request = _request(signing)
    first = signer.sign(request)
    second = signer.sign(request)
    assert first == second
    assert first.signature_b64
    assert first.audit_ref == "ci-test://corr-001/aaaaaaaaaaaa"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("digest_sha256", "b" * 64),
        ("purpose", "evidence-seal"),
        ("domain", "hermes-security-labs/other-domain"),
        ("correlation_id", "corr-002"),
    ],
)
def test_domain_separated_payload_changes_when_request_binding_changes(field: str, value: str) -> None:
    signing, adapter_module = _modules()
    base = _request(signing)
    changed = replace(base, **{field: value})
    assert adapter_module.verification_payload(base) != adapter_module.verification_payload(changed)
    signer = adapter_module.TestSignerAdapter(b"\x22" * 32)
    assert signer.sign(base).signature_b64 != signer.sign(changed).signature_b64


def test_signature_verifies_with_public_spki_and_mutation_is_rejected() -> None:
    signing, adapter_module = _modules()
    signer = adapter_module.TestSignerAdapter(b"\x33" * 32)
    request = _request(signing)
    result = signer.sign(request)
    public_key = load_der_public_key(signer.public_key_der)
    signature = base64.b64decode(result.signature_b64, validate=True)
    payload = adapter_module.verification_payload(request)
    public_key.verify(signature, payload)
    with pytest.raises(InvalidSignature):
        public_key.verify(signature, payload + b"!")


def test_result_spki_digest_matches_public_der() -> None:
    import hashlib

    signing, adapter_module = _modules()
    signer = adapter_module.TestSignerAdapter(b"\x44" * 32)
    result = signer.sign(_request(signing))
    assert result.public_key_spki_sha256 == hashlib.sha256(signer.public_key_der).hexdigest()


def test_ci_signer_is_mechanically_inadmissible_for_lab_l1() -> None:
    signing, adapter_module = _modules()
    signer = adapter_module.TestSignerAdapter(b"\x55" * 32)
    result = signer.sign(_request(signing))
    assert result.signer_class == "TEST"
    assert result.authority == "CI_ONLY/NON_AUTHORITATIVE"
    assert result.admissible_for_lab_l1 is False
    assert adapter_module.CI_ONLY is True
    assert adapter_module.NON_AUTHORITATIVE is True
    assert adapter_module.NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION is True


def test_seed_must_be_exactly_32_bytes_and_is_never_file_backed() -> None:
    _, adapter_module = _modules()
    for invalid in (b"", b"x" * 31, b"x" * 33):
        with pytest.raises(ValueError):
            adapter_module.TestSignerAdapter(invalid)


def test_adapter_imports_no_network_filesystem_or_provider_clients() -> None:
    _modules()
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    forbidden_roots = {
        "boto3",
        "hvac",
        "pkcs11",
        "requests",
        "httpx",
        "socket",
        "subprocess",
        "pathlib",
        "os",
        "shutil",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden_roots)
