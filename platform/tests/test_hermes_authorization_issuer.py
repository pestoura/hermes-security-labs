"""Repository-only tests for the Hermes TB1 authorization issuer boundary."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = ROOT / "platform/authorization-contract"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


issuer = _load("hermes_authorization_issuer_under_test", AUTH_DIR / "hermes_authorization_issuer.py")
auth = issuer.authorization_contract

CAMPAIGN_ID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_ID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP_ID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
ROE_DIGEST = "b" * 64


def _effect(**overrides: Any) -> dict[str, Any]:
    effect: dict[str, Any] = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "roe_contract_id": "roe-contract-test-001",
        "roe_contract_payload_sha256": ROE_DIGEST,
        "roe_step_request_id": "roe-step-test-001",
        "operation_id": "web.discovery.headers",
        "operation_version": "1.0.0",
        "operation_parameters": {"follow_redirects": False},
        "capability_id": "web.discovery.headers",
        "target": {"type": "lab-asset", "value": "webgoat-web"},
        "intrusiveness_level": "L1",
    }
    effect.update(overrides)
    return effect


class Ed25519Signer:
    key_id = "tb1-authorization-ed25519-test"
    algorithm = "Ed25519"

    def __init__(self) -> None:
        self.key = ed25519.Ed25519PrivateKey.generate()
        self.calls: list[bytes] = []

    def sign(self, payload: bytes) -> bytes:
        self.calls.append(payload)
        return self.key.sign(payload)


class EcdsaSigner:
    key_id = "tb1-authorization-p256-test"
    algorithm = "ECDSA-P256-SHA256"

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())

    def sign(self, payload: bytes) -> bytes:
        return self.key.sign(payload, ec.ECDSA(hashes.SHA256()))


class RecordingSigner:
    key_id = "tb1-authorization-recording-test"
    algorithm = "Ed25519"

    def __init__(self, result: bytes = b"signature") -> None:
        self.result = result
        self.calls: list[bytes] = []

    def sign(self, payload: bytes) -> bytes:
        self.calls.append(payload)
        return self.result


def _public_der(private_key: Any) -> str:
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _trust_store(tmp_path: Path, signer: Any) -> Path:
    path = tmp_path / "authorization-trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": auth.SCHEMA_VERSION,
                "domain": auth.DOMAIN,
                "purpose": auth.KEY_PURPOSE,
                "keys": [
                    {
                        "key_id": signer.key_id,
                        "algorithm": signer.algorithm,
                        "state": "active",
                        "purpose": auth.KEY_PURPOSE,
                        "public_key": _public_der(signer.key),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("signer_factory", [Ed25519Signer, EcdsaSigner])
def test_issued_receipt_is_accepted_by_existing_verifier(
    tmp_path: Path, signer_factory
) -> None:
    signer = signer_factory()
    issued = issuer.issue_authorization_receipt(_effect(), signer, ttl_seconds=300)
    verified = auth.verify_authorization_receipt(
        issued.receipt, _trust_store(tmp_path, signer)
    )

    assert verified.authorization_ref == issued.authorization_ref
    assert verified.campaign_id == CAMPAIGN_ID
    assert verified.operation_id == "web.discovery.headers"
    assert verified.capability_id == "web.discovery.headers"
    assert verified.intrusiveness_level == "L1"


def test_receipt_contains_only_identifiers_digests_and_signature() -> None:
    signer = Ed25519Signer()
    effect = _effect()
    issued = issuer.issue_authorization_receipt(effect, signer)
    serialized = json.dumps(issued.receipt, sort_keys=True)

    assert "operation_parameters" not in issued.receipt
    assert "target" not in issued.receipt
    assert "follow_redirects" not in serialized
    assert "webgoat-web" not in serialized
    assert issued.receipt["operation_parameters_sha256"] == auth.canonical_parameters_sha256(
        effect["operation_parameters"]
    )
    assert issued.receipt["target_sha256"] == issuer.gateway_contract.canonical_target_digest(
        effect["target"]
    )


def test_authority_fields_cannot_be_supplied_by_caller() -> None:
    signer = RecordingSigner()
    effect = _effect(signature={"value": "caller"})

    with pytest.raises(
        issuer.AuthorizationIssuanceError, match="ISSUER_EFFECT_FIELDS_INVALID"
    ):
        issuer.issue_authorization_receipt(effect, signer)
    assert signer.calls == []


@pytest.mark.parametrize("ttl", [0, 901, -1, True, 1.5, "300"])
def test_invalid_ttl_fails_before_signing(ttl: Any) -> None:
    signer = RecordingSigner()
    with pytest.raises(issuer.AuthorizationIssuanceError, match="ISSUER_TTL_INVALID"):
        issuer.issue_authorization_receipt(_effect(), signer, ttl_seconds=ttl)
    assert signer.calls == []


def test_malformed_target_fails_before_signing() -> None:
    signer = RecordingSigner()
    with pytest.raises(issuer.AuthorizationIssuanceError, match="ISSUER_TARGET_INVALID"):
        issuer.issue_authorization_receipt(
            _effect(target={"type": "lab-asset"}), signer
        )
    assert signer.calls == []


def test_malformed_parameters_fail_before_signing() -> None:
    signer = RecordingSigner()
    with pytest.raises(
        issuer.AuthorizationIssuanceError, match="ISSUER_PARAMETERS_INVALID"
    ):
        issuer.issue_authorization_receipt(
            _effect(operation_parameters=["not", "a", "mapping"]), signer
        )
    assert signer.calls == []


def test_invalid_uuid_fails_before_signing() -> None:
    signer = RecordingSigner()
    with pytest.raises(
        issuer.AuthorizationIssuanceError, match="ISSUER_EFFECT_UUID_INVALID"
    ):
        issuer.issue_authorization_receipt(_effect(run_id="not-a-uuid"), signer)
    assert signer.calls == []


@pytest.mark.parametrize(
    "key_id, algorithm, expected",
    [
        ("", "Ed25519", "ISSUER_SIGNER_KEY_ID_INVALID"),
        ("valid-key", "RSA", "ISSUER_SIGNER_ALGORITHM_UNSUPPORTED"),
    ],
)
def test_invalid_signer_identity_fails_closed(
    key_id: str, algorithm: str, expected: str
) -> None:
    signer = RecordingSigner()
    signer.key_id = key_id
    signer.algorithm = algorithm
    with pytest.raises(issuer.AuthorizationIssuanceError, match=expected):
        issuer.issue_authorization_receipt(_effect(), signer)
    assert signer.calls == []


def test_empty_signature_is_refused() -> None:
    signer = RecordingSigner(result=b"")
    with pytest.raises(
        issuer.AuthorizationIssuanceError, match="ISSUER_SIGNATURE_INVALID"
    ):
        issuer.issue_authorization_receipt(_effect(), signer)
    assert len(signer.calls) == 1


def test_signer_exception_is_sanitized() -> None:
    class FailingSigner(RecordingSigner):
        def sign(self, payload: bytes) -> bytes:
            self.calls.append(payload)
            raise RuntimeError("sensitive-provider-detail")

    signer = FailingSigner()
    with pytest.raises(issuer.AuthorizationIssuanceError) as exc_info:
        issuer.issue_authorization_receipt(_effect(), signer)
    assert str(exc_info.value) == "ISSUER_SIGNING_FAILED"
    assert "sensitive-provider-detail" not in str(exc_info.value)


def test_signer_receives_exact_canonical_payload_once() -> None:
    signer = Ed25519Signer()
    issued = issuer.issue_authorization_receipt(_effect(), signer)

    assert len(signer.calls) == 1
    expected = auth.canonical_signed_payload(issued.receipt)
    assert signer.calls[0] == expected


def test_summary_omits_signature_value_and_restricted_receipt() -> None:
    signer = Ed25519Signer()
    issued = issuer.issue_authorization_receipt(_effect(), signer)
    summary = issued.sanitized_summary()

    assert "receipt" not in summary
    assert "signature" not in summary
    assert issued.authorization_ref in summary.values()
    assert "signature" not in repr(issued).lower()


def test_issuer_source_contains_no_private_key_backend_or_loader() -> None:
    source = (AUTH_DIR / "hermes_authorization_issuer.py").read_text(encoding="utf-8")
    assert "from cryptography" not in source
    assert "import cryptography" not in source
    assert "load_pem_private_key" not in source
    assert "load_der_private_key" not in source
    assert "private_bytes(" not in source
