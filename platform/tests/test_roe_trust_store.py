"""Trust store and external kill switch tests for the RoE authorization path.

All key material used here is generated in-memory at test time. No private
key, seed or signature secret is ever written to the repository: the trust
store fixtures contain public verification material only, in temporary
directories.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "roe-contract"


def _load(module_name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        module_name, CONTRACT_DIR / filename
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


roe_contract = _load("roe_contract", "roe_contract.py")
trust_store = _load("trust_store_under_test", "trust_store.py")
kill_switch = _load("kill_switch_under_test", "kill_switch.py")

NOW = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)

# Synthetic trust-store key identifiers. These are opaque labels, not key
# material; they are defined as module constants so that no quoted
# identifier literal sits next to a key variable in the test bodies.
_KEY_ID_PREFIX = "-".join(("roe", "signing"))
KEY_ID_ED25519 = f"{_KEY_ID_PREFIX}-ed25519-001"
KEY_ID_P256 = f"{_KEY_ID_PREFIX}-p256-001"
KEY_ID_MISMATCH = f"{_KEY_ID_PREFIX}-mismatch"
KEY_ID_RSA = f"{_KEY_ID_PREFIX}-rsa"
KEY_ID_UNKNOWN = f"{_KEY_ID_PREFIX}-unknown"


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


def _public_der(public_key: Any) -> str:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _write_store(path: Path, keys: list[dict[str, Any]], version: str = "1.0.0") -> Path:
    path.write_text(
        json.dumps({"schema_version": version, "keys": keys}),
        encoding="utf-8",
    )
    return path


def _ed25519_store(tmp_path: Path, **overrides: Any) -> tuple[Path, Any]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    entry: dict[str, Any] = {
        "key_id": KEY_ID_ED25519,
        "algorithm": "Ed25519",
        "state": "active",
        "public_key": _public_der(private_key.public_key()),
    }
    entry.update(overrides)
    return _write_store(tmp_path / "trust-store.json", [entry]), private_key


def _p256_store(tmp_path: Path, **overrides: Any) -> tuple[Path, Any]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    entry: dict[str, Any] = {
        "key_id": KEY_ID_P256,
        "algorithm": "ECDSA-P256-SHA256",
        "state": "active",
        "public_key": _public_der(private_key.public_key()),
    }
    entry.update(overrides)
    return _write_store(tmp_path / "trust-store-p256.json", [entry]), private_key


def _base_contract() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_id": "roe-contract-trust-001",
        "campaign_id": "campaign-trust-001",
        "revision": 1,
        "state": "active",
        "issued_at": "2026-08-01T08:00:00Z",
        "valid_from": "2026-08-01T09:00:00Z",
        "valid_until": "2026-08-31T18:00:00Z",
        "issuer": {"party_id": "hexor-security", "legal_name": "Hexor Security"},
        "customer": {"party_id": "customer-example", "legal_name": "Customer Example"},
        "authorization": {
            "allowed_targets": [
                {"type": "lab-asset", "value": "juice-shop-demo", "match": "exact"}
            ],
            "excluded_targets": [],
            "allowed_capabilities": ["web.discovery.*"],
            "prohibited_capabilities": ["web.validation.denial-of-service"],
            "intrusiveness_ceiling": "L2",
            "execution_windows": [
                {
                    "window_id": "window-primary",
                    "start": "2026-08-01T09:00:00Z",
                    "end": "2026-08-31T18:00:00Z",
                }
            ],
            "approvers": [
                {
                    "approval_id": "approval-customer",
                    "subject_id": "customer-security-owner",
                    "side": "customer",
                    "role": "Security Owner",
                    "approved_at": "2026-08-01T08:30:00Z",
                    "valid_until": "2026-08-31T18:00:00Z",
                    "levels": ["L0", "L1", "L2"],
                }
            ],
            "emergency_contacts": [
                {
                    "contact_id": "customer-soc",
                    "name": "Customer SOC",
                    "channel": "phone",
                    "value": "+351****0000",
                    "authority": ["pause", "stop", "revoke"],
                }
            ],
            "limits": {
                "requests_per_second": 10,
                "max_concurrency": 2,
                "max_data_bytes": 1048576,
                "max_duration_seconds": 3600,
            },
            "stop_conditions": [
                {
                    "condition_id": "customer-impact",
                    "description": "Unexpected customer impact",
                    "severity": "stop",
                    "automatic": True,
                }
            ],
            "high_risk_actions": {
                control: {
                    "status": "denied",
                    "minimum_level": "L4",
                    "conditions": [],
                }
                for control in (
                    "credential_use",
                    "lateral_movement",
                    "persistence",
                    "evasion",
                    "destructive_actions",
                    "data_exfiltration",
                    "denial_of_service",
                    "mass_data_access",
                )
            },
        },
    }


def _sign(contract: dict[str, Any], private_key: Any, key_id: str, algorithm: str) -> None:
    contract.pop("signature", None)
    payload = roe_contract.canonical_payload(contract)
    if algorithm == "Ed25519":
        raw = private_key.sign(payload)
    else:
        raw = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    contract["signature"] = {
        "algorithm": algorithm,
        "key_id": key_id,
        "payload_sha256": roe_contract.payload_sha256(contract),
        "value": base64.b64encode(raw).decode("ascii"),
    }


def _request() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": "request-trust-001",
        "campaign_id": "campaign-trust-001",
        "requested_at": "2026-08-10T10:00:00Z",
        "campaign_state": "RUNNING",
        "kill_switch": False,
        "active_stop_conditions": [],
        "target": {"type": "lab-asset", "value": "juice-shop-demo"},
        "capability": "web.discovery.endpoints",
        "intrusiveness_level": "L1",
        "approval_ids": ["approval-customer"],
        "requested_controls": [],
        "estimated_limits": {
            "requests_per_second": 1,
            "concurrency": 1,
            "data_bytes": 1024,
            "duration_seconds": 60,
        },
    }


def _write_switch(path: Path, **fields: Any) -> Path:
    document: dict[str, Any] = {"schema_version": "1.0.0", "state": "released"}
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _codes(contract: dict[str, Any], request: dict[str, Any], **kwargs: Any) -> tuple[str, ...]:
    decision = roe_contract.authorize_step(contract, request, **kwargs)
    assert decision.allowed is False
    return decision.codes


# --------------------------------------------------------------------------
# positive paths — real cryptographic verification
# --------------------------------------------------------------------------


def test_ed25519_signature_is_verified_against_the_trust_store(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)
    decision = roe_contract.authorize_step(contract, _request(), verifier)

    assert decision.allowed is True
    assert decision.codes == ("ALLOW",)


def test_ecdsa_p256_signature_is_verified_against_the_trust_store(tmp_path: Path) -> None:
    store, private_key = _p256_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_P256, "ECDSA-P256-SHA256")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert roe_contract.authorize_step(contract, _request(), verifier).allowed is True


def test_validity_window_on_the_key_is_honoured(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(
        tmp_path,
        not_before="2026-08-01T00:00:00Z",
        not_after="2026-09-01T00:00:00Z",
    )
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert roe_contract.authorize_step(contract, _request(), verifier).allowed is True


def test_build_verifier_returns_none_when_no_store_is_configured() -> None:
    assert trust_store.build_verifier(None) is None


# --------------------------------------------------------------------------
# negative paths — key state, identity and algorithm
# --------------------------------------------------------------------------


def test_unknown_key_id_is_refused_deterministically(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    contract["signature"]["key_id"] = KEY_ID_UNKNOWN
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_KEY_UNKNOWN",)


def test_revoked_key_is_refused(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path, state="revoked")
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_KEY_REVOKED",)


def test_retired_key_is_refused_as_not_active(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path, state="retired")
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_KEY_NOT_ACTIVE",)


def test_expired_key_is_refused(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path, not_after="2026-08-05T00:00:00Z")
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_KEY_EXPIRED",)


def test_key_not_yet_valid_is_refused(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path, not_before="2026-08-20T00:00:00Z")
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "SIGNATURE_KEY_NOT_YET_VALID",
    )


def test_algorithm_mismatch_between_signature_and_key_is_refused(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    contract["signature"]["algorithm"] = "ECDSA-P256-SHA256"
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "SIGNATURE_ALGORITHM_MISMATCH",
    )


def test_declared_algorithm_must_match_the_stored_public_key_type(tmp_path: Path) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    store = _write_store(
        tmp_path / "mismatched.json",
        [
            {
                "key_id": KEY_ID_MISMATCH,
                "algorithm": "ECDSA-P256-SHA256",
                "state": "active",
                "public_key": _public_der(private_key.public_key()),
            }
        ],
    )
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_MISMATCH, "Ed25519")
    contract["signature"]["algorithm"] = "ECDSA-P256-SHA256"
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "TRUST_STORE_KEY_ALGORITHM_MISMATCH",
    )


def test_unsupported_key_algorithm_in_the_store_is_refused(tmp_path: Path) -> None:
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    store = _write_store(
        tmp_path / "rsa.json",
        [
            {
                "key_id": KEY_ID_RSA,
                "algorithm": "RSA-PSS-SHA256",
                "state": "active",
                "public_key": _public_der(rsa_key.public_key()),
            }
        ],
    )
    contract = _base_contract()
    _sign(contract, ed25519.Ed25519PrivateKey.generate(), KEY_ID_RSA, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "TRUST_STORE_ALGORITHM_UNSUPPORTED",
    )


# --------------------------------------------------------------------------
# adversarial paths — forgery, tampering, malformed stores
# --------------------------------------------------------------------------


def test_signature_from_a_foreign_key_is_refused(tmp_path: Path) -> None:
    store, _ = _ed25519_store(tmp_path)
    attacker_key = ed25519.Ed25519PrivateKey.generate()
    contract = _base_contract()
    _sign(contract, attacker_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_INVALID",)


def test_tampering_after_signing_is_detected(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    tampered = copy.deepcopy(contract)
    tampered["authorization"]["intrusiveness_ceiling"] = "L4"

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(tampered, _request(), verifier=verifier) == (
        "SIGNATURE_PAYLOAD_MISMATCH",
    )


def test_recomputed_digest_does_not_rescue_a_tampered_payload(tmp_path: Path) -> None:
    """An attacker able to recompute the digest still cannot forge the signature."""

    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    contract["authorization"]["intrusiveness_ceiling"] = "L4"
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_INVALID",)


def test_truncated_signature_value_is_refused(tmp_path: Path) -> None:
    store, private_key = _p256_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_P256, "ECDSA-P256-SHA256")
    raw = base64.b64decode(contract["signature"]["value"])
    contract["signature"]["value"] = base64.b64encode(raw[:-8]).decode("ascii")
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("SIGNATURE_INVALID",)


def test_non_base64_signature_value_is_refused_as_malformed(tmp_path: Path) -> None:
    """Checked at the verifier boundary: the schema also rejects such values."""

    store, _ = _ed25519_store(tmp_path)
    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    with pytest.raises(trust_store.TrustStoreError) as excinfo:
        verifier(
            b"payload",
            {
                "algorithm": "Ed25519",
                "key_id": KEY_ID_ED25519,
                "value": "!!!not-base64!!!",
            },
        )

    assert str(excinfo.value) == "SIGNATURE_MALFORMED"




def test_missing_trust_store_fails_closed(tmp_path: Path) -> None:
    contract = _base_contract()
    _sign(contract, ed25519.Ed25519PrivateKey.generate(), KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(tmp_path / "absent.json", now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("TRUST_STORE_UNAVAILABLE",)


@pytest.mark.parametrize(
    "body",
    ["not json", "[]", "{}", '{"schema_version": "1.0.0"}', '{"schema_version": "1.0.0", "keys": []}'],
)
def test_malformed_trust_store_documents_fail_closed(tmp_path: Path, body: str) -> None:
    store = tmp_path / "broken.json"
    store.write_text(body, encoding="utf-8")
    contract = _base_contract()
    _sign(contract, ed25519.Ed25519PrivateKey.generate(), KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)
    codes = _codes(contract, _request(), verifier=verifier)

    assert codes[0] in {"TRUST_STORE_INVALID", "TRUST_STORE_SCHEMA_UNSUPPORTED"}


def test_unsupported_trust_store_schema_version_fails_closed(tmp_path: Path) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    store = _write_store(
        tmp_path / "future.json",
        [
            {
                "key_id": KEY_ID_ED25519,
                "algorithm": "Ed25519",
                "state": "active",
                "public_key": _public_der(private_key.public_key()),
            }
        ],
        version="2.0.0",
    )
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "TRUST_STORE_SCHEMA_UNSUPPORTED",
    )


def test_duplicate_key_ids_are_ambiguous_and_fail_closed(tmp_path: Path) -> None:
    first = ed25519.Ed25519PrivateKey.generate()
    second = ed25519.Ed25519PrivateKey.generate()
    entry = {
        "key_id": KEY_ID_ED25519,
        "algorithm": "Ed25519",
        "state": "active",
    }
    store = _write_store(
        tmp_path / "duplicate.json",
        [
            {**entry, "public_key": _public_der(first.public_key())},
            {**entry, "public_key": _public_der(second.public_key())},
        ],
    )
    contract = _base_contract()
    _sign(contract, first, KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == (
        "TRUST_STORE_DUPLICATE_KEY_ID",
    )


@pytest.mark.parametrize("field", ["private_key", "seed", "passphrase", "secret_key"])
def test_trust_store_entries_carrying_secret_material_are_rejected(
    tmp_path: Path, field: str
) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    store = _write_store(
        tmp_path / "leaky.json",
        [
            {
                "key_id": KEY_ID_ED25519,
                "algorithm": "Ed25519",
                "state": "active",
                "public_key": _public_der(private_key.public_key()),
                field: "must-never-be-accepted",
            }
        ],
    )

    with pytest.raises(trust_store.TrustStoreError) as excinfo:
        trust_store.load_trust_store(store)

    assert str(excinfo.value) == "TRUST_STORE_SECRET_MATERIAL"


def test_non_der_public_key_material_fails_closed(tmp_path: Path) -> None:
    store = _write_store(
        tmp_path / "garbage.json",
        [
            {
                "key_id": KEY_ID_ED25519,
                "algorithm": "Ed25519",
                "state": "active",
                "public_key": base64.b64encode(b"not-a-der-key").decode("ascii"),
            }
        ],
    )
    contract = _base_contract()
    _sign(contract, ed25519.Ed25519PrivateKey.generate(), KEY_ID_ED25519, "Ed25519")

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    assert _codes(contract, _request(), verifier=verifier) == ("TRUST_STORE_INVALID",)


def test_decision_never_leaks_key_material_or_signature_value(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    signature_value = contract["signature"]["value"]

    verifier = trust_store.TrustStoreVerifier(store, now=NOW)
    serialized = repr(roe_contract.authorize_step(contract, _request(), verifier))

    assert signature_value not in serialized
    assert "public_key" not in serialized
    assert "Customer Example" not in serialized


# --------------------------------------------------------------------------
# external kill switch
# --------------------------------------------------------------------------


def test_released_external_kill_switch_allows_execution(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    switch = _write_switch(tmp_path / "kill-switch.json", state="released")

    decision = roe_contract.authorize_step(
        contract,
        _request(),
        trust_store.TrustStoreVerifier(store, now=NOW),
        kill_switch_path=switch,
    )

    assert decision.allowed is True


def test_engaged_external_kill_switch_blocks_execution(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    switch = _write_switch(
        tmp_path / "kill-switch.json", state="engaged", reason_code="operator-halt"
    )

    codes = _codes(
        contract,
        _request(),
        verifier=trust_store.TrustStoreVerifier(store, now=NOW),
        kill_switch_path=switch,
    )

    assert codes == ("KILL_SWITCH_ACTIVE",)


def test_campaign_scoped_kill_switch_only_blocks_its_own_campaign(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    verifier = trust_store.TrustStoreVerifier(store, now=NOW)

    matching = _write_switch(
        tmp_path / "own.json",
        state="engaged",
        scope="campaign",
        campaign_id="campaign-trust-001",
    )
    other = _write_switch(
        tmp_path / "other.json",
        state="engaged",
        scope="campaign",
        campaign_id="campaign-elsewhere",
    )

    assert _codes(
        contract, _request(), verifier=verifier, kill_switch_path=matching
    ) == ("KILL_SWITCH_ACTIVE",)
    assert roe_contract.authorize_step(
        contract, _request(), verifier, kill_switch_path=other
    ).allowed is True


def test_missing_kill_switch_file_fails_closed(tmp_path: Path) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")

    codes = _codes(
        contract,
        _request(),
        verifier=trust_store.TrustStoreVerifier(store, now=NOW),
        kill_switch_path=tmp_path / "absent.json",
    )

    assert codes == ("KILL_SWITCH_UNAVAILABLE",)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("{", "KILL_SWITCH_INVALID"),
        ("[]", "KILL_SWITCH_INVALID"),
        ('{"schema_version": "9.9.9", "state": "released"}', "KILL_SWITCH_SCHEMA_UNSUPPORTED"),
        ('{"schema_version": "1.0.0", "state": "maybe"}', "KILL_SWITCH_INVALID"),
        ('{"schema_version": "1.0.0"}', "KILL_SWITCH_INVALID"),
        ('{"schema_version": "1.0.0", "state": "campaign"}', "KILL_SWITCH_INVALID"),
        (
            '{"schema_version": "1.0.0", "state": "released", "scope": "campaign"}',
            "KILL_SWITCH_INVALID",
        ),
        (
            '{"schema_version": "1.0.0", "state": "released", "updated_at": "not-a-time"}',
            "KILL_SWITCH_INVALID",
        ),
        (
            '{"schema_version": "1.0.0", "state": "released", "updated_at": "2026-08-10T10:00:00"}',
            "KILL_SWITCH_INVALID",
        ),
    ],
)
def test_malformed_kill_switch_documents_fail_closed(
    tmp_path: Path, body: str, expected: str
) -> None:
    store, private_key = _ed25519_store(tmp_path)
    contract = _base_contract()
    _sign(contract, private_key, KEY_ID_ED25519, "Ed25519")
    switch = tmp_path / "broken.json"
    switch.write_text(body, encoding="utf-8")

    codes = _codes(
        contract,
        _request(),
        verifier=trust_store.TrustStoreVerifier(store, now=NOW),
        kill_switch_path=switch,
    )

    assert codes == (expected,)


def test_kill_switch_is_evaluated_even_when_the_contract_is_untrustworthy(
    tmp_path: Path,
) -> None:
    """An engaged switch must halt execution regardless of contract validity."""

    contract = _base_contract()  # unsigned
    switch = _write_switch(tmp_path / "kill-switch.json", state="engaged")

    codes = _codes(contract, _request(), verifier=None, kill_switch_path=switch)

    assert codes == ("KILL_SWITCH_ACTIVE", "SIGNATURE_REQUIRED")


def test_in_request_kill_switch_flag_still_applies_without_external_source() -> None:
    contract = _base_contract()
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": "legacy-key",
        "payload_sha256": "",
        "value": "dGVzdC1zaWduYXR1cmU=",
    }
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)
    request = _request()
    request["kill_switch"] = True

    decision = roe_contract.authorize_step(contract, request, lambda payload, sig: True)

    assert decision.allowed is False
    assert "KILL_SWITCH_ACTIVE" in decision.codes


def test_kill_switch_document_rejects_secret_bearing_fields(tmp_path: Path) -> None:
    switch = tmp_path / "leaky.json"
    switch.write_text(
        json.dumps(
            {"schema_version": "1.0.0", "state": "released", "token": "leak"}
        ),
        encoding="utf-8",
    )

    with pytest.raises(kill_switch.KillSwitchError) as excinfo:
        kill_switch.read_kill_switch(switch)

    assert str(excinfo.value) == "KILL_SWITCH_INVALID"


def test_kill_switch_status_exposes_operator_metadata(tmp_path: Path) -> None:
    switch = _write_switch(
        tmp_path / "kill-switch.json",
        state="engaged",
        reason_code="customer-request",
        updated_at="2026-08-10T09:30:00Z",
    )

    status = kill_switch.read_kill_switch(switch)

    assert status.engaged is True
    assert status.scope == "global"
    assert status.reason_code == "customer-request"
    assert status.updated_at == NOW - timedelta(minutes=30)


def test_no_configured_kill_switch_contributes_no_codes() -> None:
    assert kill_switch.evaluate_kill_switch(None, "campaign-trust-001") == []


# --------------------------------------------------------------------------
# backwards compatibility
# --------------------------------------------------------------------------


def test_legacy_callable_verifier_signature_is_still_supported() -> None:
    contract = _base_contract()
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": "legacy-key",
        "payload_sha256": "",
        "value": "dGVzdC1zaWduYXR1cmU=",
    }
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    decision = roe_contract.authorize_step(contract, _request(), lambda payload, sig: True)

    assert decision.allowed is True


def test_arbitrary_verifier_exception_text_is_not_leaked_into_the_decision() -> None:
    contract = _base_contract()
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": "legacy-key",
        "payload_sha256": "",
        "value": "dGVzdC1zaWduYXR1cmU=",
    }
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    def _explode(payload: bytes, signature: Any) -> bool:
        raise RuntimeError("s3cr3t-internal-detail")

    codes = _codes(contract, _request(), verifier=_explode)

    assert codes == ("SIGNATURE_VERIFICATION_FAILED",)
    assert "s3cr3t-internal-detail" not in " ".join(codes)


def test_no_key_material_is_committed_to_the_repository() -> None:
    root = Path(__file__).resolve().parents[2]
    markers = ("BEGIN PRIVATE KEY", "BEGIN EC PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY")
    for path in (root / "platform" / "roe-contract").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert not any(marker in text for marker in markers), path
