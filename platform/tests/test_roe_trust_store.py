"""Tests for the file-backed RoE trust store and kill-switch state.

No private key material is committed: every key pair used here is generated in
memory at test time and discarded with the temporary directory.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "roe-contract"


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, CONTRACT_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


trust_store = _load("roe_trust_store_under_test", "roe_trust_store.py")
roe_contract = _load("roe_contract_under_test", "roe_contract.py")

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, ed25519  # noqa: E402

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _spki(public_key: Any) -> str:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _ed25519_pair() -> tuple[Any, str]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    return private_key, _spki(private_key.public_key())


def _p256_pair() -> tuple[Any, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, _spki(private_key.public_key())


def _sign(private_key: Any, payload: bytes, algorithm: str) -> str:
    if algorithm == "Ed25519":
        raw = private_key.sign(payload)
    else:
        raw = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(raw).decode("ascii")


def _store_document(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "1.0.0", "store_id": "hexor-roe", "keys": entries}


def _key_entry(
    key_id: str,
    algorithm: str,
    spki: str,
    *,
    state: str = "active",
    not_before: str = "2026-01-01T00:00:00Z",
    not_after: str = "2027-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "key_id": key_id,
        "algorithm": algorithm,
        "state": state,
        "not_before": not_before,
        "not_after": not_after,
        "public_key_spki_base64": spki,
    }


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# --- trust store loading -------------------------------------------------


def test_active_ed25519_key_resolves_uniquely(tmp_path: Path) -> None:
    _, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "Ed25519", spki)]),
    )
    store = trust_store.TrustStore.load(path)

    assert store.key_ids() == ("roe-key-1",)
    key = store.resolve("roe-key-1", "Ed25519", NOW)
    assert key.algorithm == "Ed25519"
    assert key.state == "active"


def test_missing_trust_store_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(trust_store.TrustStoreError, match="TRUST_STORE_UNAVAILABLE"):
        trust_store.TrustStore.load(tmp_path / "absent.json")


def test_malformed_trust_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "trust.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(trust_store.TrustStoreError, match="TRUST_STORE_MALFORMED"):
        trust_store.TrustStore.load(path)


def test_schema_invalid_trust_store_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path / "trust.json", {"schema_version": "1.0.0", "keys": []})
    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_SCHEMA_INVALID"
    ):
        trust_store.TrustStore.load(path)


def test_duplicate_key_id_is_rejected_so_resolution_is_unambiguous(
    tmp_path: Path,
) -> None:
    _, first = _ed25519_pair()
    _, second = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document(
            [
                _key_entry("roe-key-1", "Ed25519", first),
                _key_entry("roe-key-1", "Ed25519", second),
            ]
        ),
    )
    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_DUPLICATE_KEY_ID"
    ):
        trust_store.TrustStore.load(path)


def test_public_key_material_that_is_not_valid_spki_is_rejected(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "trust.json",
        _store_document(
            [_key_entry("roe-key-1", "Ed25519", base64.b64encode(b"A" * 48).decode())]
        ),
    )
    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_INVALID_PUBLIC_KEY"
    ):
        trust_store.TrustStore.load(path)


def test_declared_algorithm_must_match_key_material(tmp_path: Path) -> None:
    _, ed_spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "ECDSA-P256-SHA256", ed_spki)]),
    )
    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_ALGORITHM_MISMATCH"
    ):
        trust_store.TrustStore.load(path)


def test_inverted_validity_window_is_rejected(tmp_path: Path) -> None:
    _, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document(
            [
                _key_entry(
                    "roe-key-1",
                    "Ed25519",
                    spki,
                    not_before="2027-01-01T00:00:00Z",
                    not_after="2026-01-01T00:00:00Z",
                )
            ]
        ),
    )
    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_INVALID_VALIDITY"
    ):
        trust_store.TrustStore.load(path)


# --- resolution refusals -------------------------------------------------


@pytest.mark.parametrize(
    ("entry_kwargs", "key_id", "algorithm", "expected"),
    [
        ({}, "unknown-key", "Ed25519", "TRUST_STORE_KEY_UNKNOWN"),
        ({"state": "revoked"}, "roe-key-1", "Ed25519", "TRUST_STORE_KEY_REVOKED"),
        (
            {
                "not_before": "2020-01-01T00:00:00Z",
                "not_after": "2021-01-01T00:00:00Z",
            },
            "roe-key-1",
            "Ed25519",
            "TRUST_STORE_KEY_EXPIRED",
        ),
        (
            {},
            "roe-key-1",
            "ECDSA-P256-SHA256",
            "TRUST_STORE_ALGORITHM_MISMATCH",
        ),
    ],
)
def test_resolution_refuses_deterministically(
    tmp_path: Path,
    entry_kwargs: dict[str, Any],
    key_id: str,
    algorithm: str,
    expected: str,
) -> None:
    _, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "Ed25519", spki, **entry_kwargs)]),
    )
    store = trust_store.TrustStore.load(path)
    with pytest.raises(trust_store.TrustStoreError, match=expected):
        store.resolve(key_id, algorithm, NOW)


# --- real cryptographic verification -------------------------------------


@pytest.mark.parametrize("algorithm", ["Ed25519", "ECDSA-P256-SHA256"])
def test_real_signature_verification_round_trip(
    tmp_path: Path, algorithm: str
) -> None:
    private_key, spki = (
        _ed25519_pair() if algorithm == "Ed25519" else _p256_pair()
    )
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", algorithm, spki)]),
    )
    store = trust_store.TrustStore.load(path)
    payload = b"canonical-payload"
    signature = {
        "algorithm": algorithm,
        "key_id": "roe-key-1",
        "value": _sign(private_key, payload, algorithm),
    }

    assert trust_store.verify_with_trust_store(store, payload, signature, NOW) is True
    assert (
        trust_store.verify_with_trust_store(store, b"tampered", signature, NOW) is False
    )


def test_signature_from_a_foreign_key_is_rejected(tmp_path: Path) -> None:
    _, spki = _ed25519_pair()
    attacker_key, _ = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "Ed25519", spki)]),
    )
    store = trust_store.TrustStore.load(path)
    payload = b"canonical-payload"
    signature = {
        "algorithm": "Ed25519",
        "key_id": "roe-key-1",
        "value": _sign(attacker_key, payload, "Ed25519"),
    }

    assert trust_store.verify_with_trust_store(store, payload, signature, NOW) is False


def test_cross_algorithm_signature_confusion_is_rejected(tmp_path: Path) -> None:
    ec_key, ec_spki = _p256_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "ECDSA-P256-SHA256", ec_spki)]),
    )
    store = trust_store.TrustStore.load(path)
    payload = b"canonical-payload"
    signature = {
        "algorithm": "Ed25519",
        "key_id": "roe-key-1",
        "value": _sign(ec_key, payload, "ECDSA-P256-SHA256"),
    }

    with pytest.raises(
        trust_store.TrustStoreError, match="TRUST_STORE_ALGORITHM_MISMATCH"
    ):
        trust_store.verify_with_trust_store(store, payload, signature, NOW)


def test_non_base64_signature_value_fails_closed(tmp_path: Path) -> None:
    _, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "Ed25519", spki)]),
    )
    store = trust_store.TrustStore.load(path)
    signature = {"algorithm": "Ed25519", "key_id": "roe-key-1", "value": "!!!"}

    with pytest.raises(
        trust_store.TrustStoreError, match="SIGNATURE_ENCODING_INVALID"
    ):
        trust_store.verify_with_trust_store(store, b"payload", signature, NOW)


def test_truncated_signature_is_rejected_not_accepted(tmp_path: Path) -> None:
    private_key, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document([_key_entry("roe-key-1", "Ed25519", spki)]),
    )
    store = trust_store.TrustStore.load(path)
    payload = b"canonical-payload"
    raw = base64.b64decode(_sign(private_key, payload, "Ed25519"))
    signature = {
        "algorithm": "Ed25519",
        "key_id": "roe-key-1",
        "value": base64.b64encode(raw[:-4]).decode("ascii"),
    }

    assert trust_store.verify_with_trust_store(store, payload, signature, NOW) is False


# --- kill switch ---------------------------------------------------------


def test_armed_kill_switch_does_not_block(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "kill.json",
        {
            "schema_version": "1.0.0",
            "state": "armed",
            "updated_at": "2026-08-10T00:00:00Z",
        },
    )
    state = trust_store.load_kill_switch_state(path)

    assert state.engaged is False
    assert state.applies_to("campaign-001") is False


def test_engaged_global_kill_switch_applies_to_every_campaign(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "kill.json",
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T00:00:00Z",
            "reason_code": "OPERATOR_STOP",
        },
    )
    state = trust_store.load_kill_switch_state(path)

    assert state.applies_to("campaign-001") is True
    assert state.applies_to("campaign-002") is True


def test_scoped_kill_switch_only_applies_to_its_campaign(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "kill.json",
        {
            "schema_version": "1.0.0",
            "state": "engaged",
            "updated_at": "2026-08-10T00:00:00Z",
            "scope": {"campaign_id": "campaign-001"},
        },
    )
    state = trust_store.load_kill_switch_state(path)

    assert state.applies_to("campaign-001") is True
    assert state.applies_to("campaign-002") is False


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("{broken", "KILL_SWITCH_MALFORMED"),
        (json.dumps({"schema_version": "1.0.0", "state": "on"}), "KILL_SWITCH_SCHEMA_INVALID"),
    ],
)
def test_invalid_kill_switch_state_fails_closed(
    tmp_path: Path, payload: str, expected: str
) -> None:
    path = tmp_path / "kill.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(trust_store.TrustStoreError, match=expected):
        trust_store.load_kill_switch_state(path)


def test_missing_kill_switch_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(trust_store.TrustStoreError, match="KILL_SWITCH_UNAVAILABLE"):
        trust_store.load_kill_switch_state(tmp_path / "absent.json")


# --- trust store must never carry secrets --------------------------------


def test_repository_contains_no_private_key_material() -> None:
    for path in CONTRACT_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "PRIVATE KEY" not in text, path.name


def test_trusted_key_validity_boundaries_are_half_open(tmp_path: Path) -> None:
    _, spki = _ed25519_pair()
    path = _write(
        tmp_path / "trust.json",
        _store_document(
            [
                _key_entry(
                    "roe-key-1",
                    "Ed25519",
                    spki,
                    not_before="2026-08-10T12:00:00Z",
                    not_after="2026-08-10T13:00:00Z",
                )
            ]
        ),
    )
    store = trust_store.TrustStore.load(path)

    assert store.resolve("roe-key-1", "Ed25519", NOW).key_id == "roe-key-1"
    with pytest.raises(trust_store.TrustStoreError, match="TRUST_STORE_KEY_EXPIRED"):
        store.resolve("roe-key-1", "Ed25519", NOW - timedelta(seconds=1))
    with pytest.raises(trust_store.TrustStoreError, match="TRUST_STORE_KEY_EXPIRED"):
        store.resolve("roe-key-1", "Ed25519", NOW + timedelta(hours=1))


def test_committed_example_trust_store_loads_and_resolves() -> None:
    store = trust_store.TrustStore.load(
        CONTRACT_DIR / "examples" / "trust-store.example.json"
    )

    assert store.resolve("customer-signing-key-01", "Ed25519", NOW).state == "active"
    assert (
        store.resolve("provider-signing-key-01", "ECDSA-P256-SHA256", NOW).algorithm
        == "ECDSA-P256-SHA256"
    )
    with pytest.raises(trust_store.TrustStoreError, match="TRUST_STORE_KEY_REVOKED"):
        store.resolve("customer-signing-key-00", "Ed25519", NOW)


def test_committed_example_kill_switch_is_armed() -> None:
    state = trust_store.load_kill_switch_state(
        CONTRACT_DIR / "examples" / "kill-switch.example.json"
    )

    assert state.engaged is False
