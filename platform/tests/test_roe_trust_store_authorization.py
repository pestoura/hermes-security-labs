"""Integration tests: trust store + kill switch inside the authorization path.

These exercise `authorize_step` with a real Ed25519/ECDSA-P256 signature and a
file-backed kill switch. All key material is generated in memory per test.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
CONTRACT_DIR = TESTS_DIR.parent / "roe-contract"

_contract_spec = importlib.util.spec_from_file_location(
    "roe_contract_integration", CONTRACT_DIR / "roe_contract.py"
)
assert _contract_spec and _contract_spec.loader
roe_contract = importlib.util.module_from_spec(_contract_spec)
sys.modules[_contract_spec.name] = roe_contract
_contract_spec.loader.exec_module(roe_contract)

_base_spec = importlib.util.spec_from_file_location(
    "roe_contract_fixtures", TESTS_DIR / "test_roe_contract.py"
)
assert _base_spec and _base_spec.loader
_fixtures = importlib.util.module_from_spec(_base_spec)
sys.modules[_base_spec.name] = _fixtures
_base_spec.loader.exec_module(_fixtures)

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, ed25519  # noqa: E402

NOW = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)


def _spki_b64(public_key: Any) -> str:
    return base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")


def _generate(algorithm: str) -> tuple[Any, str]:
    if algorithm == "Ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, _spki_b64(private_key.public_key())


def _sign(private_key: Any, payload: bytes, algorithm: str) -> str:
    if algorithm == "Ed25519":
        raw = private_key.sign(payload)
    else:
        raw = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(raw).decode("ascii")


def _trust_file(
    tmp_path: Path,
    key_id: str,
    algorithm: str,
    spki: str,
    *,
    state: str = "active",
    not_before: str = "2026-01-01T00:00:00Z",
    not_after: str = "2027-01-01T00:00:00Z",
) -> Path:
    path = tmp_path / "trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": key_id,
                        "algorithm": algorithm,
                        "state": state,
                        "not_before": not_before,
                        "not_after": not_after,
                        "public_key_spki_base64": spki,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _signed_contract(private_key: Any, algorithm: str, key_id: str) -> dict[str, Any]:
    contract = _fixtures._contract()
    contract.pop("signature", None)
    payload = roe_contract.canonical_payload(contract)
    contract["signature"] = {
        "algorithm": algorithm,
        "key_id": key_id,
        "payload_sha256": roe_contract.payload_sha256(contract),
        "value": _sign(private_key, payload, algorithm),
    }
    return contract


def _kill_file(tmp_path: Path, document: Any, name: str = "kill.json") -> Path:
    path = tmp_path / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8",
    )
    return path


# --- positive ------------------------------------------------------------


@pytest.mark.parametrize("algorithm", ["Ed25519", "ECDSA-P256-SHA256"])
def test_step_is_allowed_with_a_real_signature_from_the_trust_store(
    tmp_path: Path, algorithm: str
) -> None:
    private_key, spki = _generate(algorithm)
    trust_path = _trust_file(tmp_path, "roe-key-1", algorithm, spki)
    contract = _signed_contract(private_key, algorithm, "roe-key-1")

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
    )

    assert decision.allowed is True
    assert decision.codes == ("ALLOW",)


def test_explicit_verifier_still_takes_precedence_backwards_compatible() -> None:
    decision = roe_contract.authorize_step(
        _fixtures._contract(), _fixtures._request(), _fixtures._verifier
    )

    assert decision.allowed is True


def test_no_verifier_and_no_trust_store_still_fails_closed() -> None:
    decision = roe_contract.authorize_step(_fixtures._contract(), _fixtures._request())

    assert decision.allowed is False
    assert decision.codes == ("SIGNATURE_VERIFIER_UNAVAILABLE",)


# --- negative: trust store -----------------------------------------------


def test_unknown_key_id_refuses_deterministically(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "other-key", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.allowed is False
    assert decision.codes == ("TRUST_STORE_KEY_UNKNOWN",)


def test_revoked_key_refuses(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(
        tmp_path, "roe-key-1", "Ed25519", spki, state="revoked"
    )
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.codes == ("TRUST_STORE_KEY_REVOKED",)


def test_expired_key_refuses(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(
        tmp_path,
        "roe-key-1",
        "Ed25519",
        spki,
        not_before="2020-01-01T00:00:00Z",
        not_after="2021-01-01T00:00:00Z",
    )
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.codes == ("TRUST_STORE_KEY_EXPIRED",)


def test_algorithm_mismatch_refuses(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    ec_key, ec_spki = _generate("ECDSA-P256-SHA256")
    trust_path = _trust_file(tmp_path, "roe-key-1", "ECDSA-P256-SHA256", ec_spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.codes == ("TRUST_STORE_ALGORITHM_MISMATCH",)


def test_missing_trust_store_file_refuses(tmp_path: Path) -> None:
    private_key, _ = _generate("Ed25519")
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=tmp_path / "absent.json"
    )

    assert decision.codes == ("TRUST_STORE_UNAVAILABLE",)


def test_signature_forged_by_another_key_refuses(tmp_path: Path) -> None:
    _, spki = _generate("Ed25519")
    attacker_key, _ = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(attacker_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.codes == ("SIGNATURE_INVALID",)


def test_payload_tampering_after_signing_refuses(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    contract["authorization"]["allowed_capabilities"].append("web.validation.*")
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)

    decision = roe_contract.authorize_step(
        contract, _fixtures._request(), trust_store_path=trust_path
    )

    assert decision.codes == ("SIGNATURE_INVALID",)


# --- kill switch in the authorization path -------------------------------


def test_engaged_kill_switch_blocks_an_otherwise_valid_step(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    kill_path = _kill_file(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T09:00:00Z",
            "reason_code": "OPERATOR_STOP",
        },
    )

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )

    assert decision.allowed is False
    assert decision.codes == ("KILL_SWITCH_ENGAGED",)


def test_armed_kill_switch_allows_the_step(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    kill_path = _kill_file(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "state": "armed",
            "updated_at": "2026-08-10T09:00:00Z",
        },
    )

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )

    assert decision.allowed is True


def test_kill_switch_scoped_to_another_campaign_does_not_block(
    tmp_path: Path,
) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    kill_path = _kill_file(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T09:00:00Z",
            "scope": {"campaign_id": "campaign-999"},
        },
    )

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )

    assert decision.allowed is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("{broken", "KILL_SWITCH_MALFORMED"),
        (
            json.dumps({"schema_version": "1.0.0", "state": "engaged"}),
            "KILL_SWITCH_SCHEMA_INVALID",
        ),
    ],
)
def test_configured_but_invalid_kill_switch_fails_closed(
    tmp_path: Path, payload: str, expected: str
) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    kill_path = _kill_file(tmp_path, payload)

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )

    assert decision.allowed is False
    assert decision.codes == (expected,)


def test_configured_but_missing_kill_switch_fails_closed(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=tmp_path / "absent.json",
    )

    assert decision.allowed is False
    assert decision.codes == ("KILL_SWITCH_UNAVAILABLE",)


def test_request_kill_switch_and_external_state_both_reported(
    tmp_path: Path,
) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    request = _fixtures._request()
    request["kill_switch"] = True
    kill_path = _kill_file(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T09:00:00Z",
        },
    )

    decision = roe_contract.authorize_step(
        contract,
        request,
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )

    assert decision.allowed is False
    assert set(decision.codes) == {"KILL_SWITCH_ACTIVE", "KILL_SWITCH_ENGAGED"}


def test_decision_never_leaks_key_or_kill_switch_material(tmp_path: Path) -> None:
    private_key, spki = _generate("Ed25519")
    trust_path = _trust_file(tmp_path, "roe-key-1", "Ed25519", spki)
    contract = _signed_contract(private_key, "Ed25519", "roe-key-1")
    kill_path = _kill_file(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T09:00:00Z",
            "reason_code": "OPERATOR_STOP",
        },
    )

    decision = roe_contract.authorize_step(
        contract,
        _fixtures._request(),
        trust_store_path=trust_path,
        kill_switch_path=kill_path,
    )
    rendered = repr(decision)

    assert spki not in rendered
    assert contract["signature"]["value"] not in rendered
    assert str(trust_path) not in rendered
    assert "OPERATOR_STOP" not in rendered
