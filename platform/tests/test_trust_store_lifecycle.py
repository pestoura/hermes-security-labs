from __future__ import annotations

import base64
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/roe-contract/trust_store_lifecycle.py"
SCHEMA_DIR = ROOT / "platform/roe-contract"

spec = importlib.util.spec_from_file_location("trust_store_lifecycle_contract", MODULE_PATH)
assert spec and spec.loader
lifecycle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lifecycle
spec.loader.exec_module(lifecycle)

NOW = "2026-08-08T02:30:00Z"


def key(
    key_id: str,
    *,
    state: str = "active",
    algorithm: str = "Ed25519",
    material: bytes | None = None,
    not_before: str | None = "2026-08-01T00:00:00Z",
    not_after: str | None = "2027-08-01T00:00:00Z",
) -> dict:
    payload = material if material is not None else (f"public-{key_id}".encode())
    return {
        "key_id": key_id,
        "algorithm": algorithm,
        "public_key": base64.b64encode(payload).decode("ascii"),
        "state": state,
        "not_before": not_before,
        "not_after": not_after,
    }


def write_store(path: Path, *keys: dict) -> Path:
    path.write_text(
        json.dumps({"schema_version": "1.0.0", "keys": list(keys)}, sort_keys=True),
        encoding="utf-8",
    )
    return path


def generation(
    path: Path,
    *,
    sequence: int = 1,
    generated_at: str = "2026-08-08T02:29:30Z",
    previous_generation_id: str | None = None,
) -> dict:
    return lifecycle.build_generation(
        trust_store_path=path,
        sequence=sequence,
        generated_at=generated_at,
        previous_generation_id=previous_generation_id,
    )


def schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_initial_generation_is_content_addressed_fresh_and_review_only(tmp_path: Path) -> None:
    store = write_store(tmp_path / "store.json", key("key-a"))
    current = generation(store)
    assessment = lifecycle.assess_transition(
        previous=None, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    lifecycle.validate_generation(current)
    jsonschema.validate(current, schema("trust-store-generation.schema.json"))
    jsonschema.validate(
        assessment, schema("trust-store-lifecycle-assessment.schema.json")
    )
    assert assessment["decision"] == "ACCEPT_FOR_REVIEW"
    assert assessment["codes"] == []
    assert assessment["freshness_state"] == "FRESH"
    assert assessment["rollback_detected"] is False
    assert assessment["active_key_count"] == 1
    assert assessment["automatic_activation"] is False
    assert assessment["activation_effect"] == "NONE"
    assert assessment["authorization_effect"] == "NONE"
    assert assessment["execution_authority"] == "NONE"
    assert "public_key" not in current["keys"][0]
    assert "public_key_sha256" in current["keys"][0]


def test_safe_rotation_retires_old_key_and_adds_new_active_key(tmp_path: Path) -> None:
    old_store = write_store(tmp_path / "old.json", key("key-a", state="active"))
    previous = generation(old_store)
    new_store = write_store(
        tmp_path / "new.json",
        key("key-a", state="retired"),
        key("key-b", state="active"),
    )
    current = generation(
        new_store,
        sequence=2,
        generated_at="2026-08-08T02:29:40Z",
        previous_generation_id=previous["generation_id"],
    )
    assessment = lifecycle.assess_transition(
        previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "ACCEPT_FOR_REVIEW"
    assert assessment["codes"] == []
    assert assessment["added_key_ids"] == ["key-b"]
    assert assessment["state_changes"] == [
        {"key_id": "key-a", "from": "active", "to": "retired"}
    ]


@pytest.mark.parametrize("old_state", ["retired", "revoked"])
def test_nonactive_key_cannot_be_resurrected(tmp_path: Path, old_state: str) -> None:
    old = write_store(tmp_path / "old.json", key("key-a", state=old_state), key("key-b"))
    previous = generation(old)
    new = write_store(tmp_path / "new.json", key("key-a", state="active"), key("key-b"))
    current = generation(
        new,
        sequence=2,
        generated_at="2026-08-08T02:29:40Z",
        previous_generation_id=previous["generation_id"],
    )
    assessment = lifecycle.assess_transition(
        previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "REFUSE"
    assert "TRUST_STORE_KEY_STATE_RESURRECTION" in assessment["codes"]


def test_key_material_algorithm_and_validity_mutation_fail_closed(tmp_path: Path) -> None:
    previous_store = write_store(tmp_path / "old.json", key("key-a"))
    previous = generation(previous_store)

    mutation_cases = [
        key("key-a", material=b"different-material"),
        key("key-a", algorithm="ECDSA-P256-SHA256"),
        key("key-a", not_after="2028-08-01T00:00:00Z"),
    ]
    expected_codes = [
        "TRUST_STORE_KEY_MATERIAL_MUTATION",
        "TRUST_STORE_KEY_ALGORITHM_MUTATION",
        "TRUST_STORE_KEY_VALIDITY_MUTATION",
    ]
    for index, (mutated, expected) in enumerate(zip(mutation_cases, expected_codes), start=1):
        new_store = write_store(tmp_path / f"new-{index}.json", mutated)
        current = generation(
            new_store,
            sequence=2,
            generated_at="2026-08-08T02:29:40Z",
            previous_generation_id=previous["generation_id"],
        )
        assessment = lifecycle.assess_transition(
            previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
        )
        assert assessment["decision"] == "REFUSE"
        assert expected in assessment["codes"]


def test_active_key_removal_fails_closed(tmp_path: Path) -> None:
    previous_store = write_store(tmp_path / "old.json", key("key-a"), key("key-b"))
    previous = generation(previous_store)
    current_store = write_store(tmp_path / "new.json", key("key-b"))
    current = generation(
        current_store,
        sequence=2,
        generated_at="2026-08-08T02:29:40Z",
        previous_generation_id=previous["generation_id"],
    )
    assessment = lifecycle.assess_transition(
        previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "REFUSE"
    assert assessment["removed_key_ids"] == ["key-a"]
    assert "TRUST_STORE_ACTIVE_KEY_REMOVED" in assessment["codes"]


def test_sequence_gap_predecessor_mismatch_and_time_rollback_are_refused(tmp_path: Path) -> None:
    previous_store = write_store(tmp_path / "old.json", key("key-a"))
    previous = generation(previous_store, generated_at="2026-08-08T02:29:20Z")
    current_store = write_store(tmp_path / "new.json", key("key-a"), key("key-b"))

    current = generation(
        current_store,
        sequence=3,
        generated_at="2026-08-08T02:29:10Z",
        previous_generation_id="tsg_" + "f" * 32,
    )
    assessment = lifecycle.assess_transition(
        previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "REFUSE"
    assert assessment["rollback_detected"] is True
    assert "TRUST_STORE_SEQUENCE_NON_MONOTONIC" in assessment["codes"]
    assert "TRUST_STORE_PREDECESSOR_MISMATCH" in assessment["codes"]
    assert "TRUST_STORE_GENERATED_AT_NON_MONOTONIC" in assessment["codes"]


@pytest.mark.parametrize(
    ("generated_at", "expected_state", "expected_code"),
    [
        ("2026-08-08T02:00:00Z", "STALE", "TRUST_STORE_GENERATION_STALE"),
        ("2026-08-08T02:31:00Z", "FUTURE", "TRUST_STORE_GENERATION_FUTURE"),
    ],
)
def test_stale_or_future_generation_is_refused(
    tmp_path: Path, generated_at: str, expected_state: str, expected_code: str
) -> None:
    store = write_store(tmp_path / "store.json", key("key-a"))
    current = generation(store, generated_at=generated_at)
    assessment = lifecycle.assess_transition(
        previous=None, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "REFUSE"
    assert assessment["freshness_state"] == expected_state
    assert expected_code in assessment["codes"]


def test_generation_manifest_tampering_fails_closed(tmp_path: Path) -> None:
    store = write_store(tmp_path / "store.json", key("key-a"))
    current = generation(store)
    tampered = deepcopy(current)
    tampered["keys"][0]["state"] = "revoked"
    with pytest.raises(lifecycle.TrustStoreLifecycleError, match="generation id"):
        lifecycle.assess_transition(
            previous=None, current=tampered, evaluated_at=NOW, max_age_seconds=60
        )


def test_all_keys_nonactive_refuses_generation(tmp_path: Path) -> None:
    store = write_store(
        tmp_path / "store.json",
        key("key-a", state="retired"),
        key("key-b", state="revoked"),
    )
    current = generation(store)
    assessment = lifecycle.assess_transition(
        previous=None, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "REFUSE"
    assert assessment["active_key_count"] == 0
    assert "TRUST_STORE_NO_ACTIVE_KEYS" in assessment["codes"]


def test_retired_or_revoked_key_can_be_removed_but_does_not_activate_generation(tmp_path: Path) -> None:
    previous_store = write_store(
        tmp_path / "old.json",
        key("key-a", state="retired"),
        key("key-b", state="active"),
    )
    previous = generation(previous_store)
    current_store = write_store(tmp_path / "new.json", key("key-b", state="active"))
    current = generation(
        current_store,
        sequence=2,
        generated_at="2026-08-08T02:29:40Z",
        previous_generation_id=previous["generation_id"],
    )
    assessment = lifecycle.assess_transition(
        previous=previous, current=current, evaluated_at=NOW, max_age_seconds=60
    )
    assert assessment["decision"] == "ACCEPT_FOR_REVIEW"
    assert assessment["removed_key_ids"] == ["key-a"]
    assert assessment["automatic_activation"] is False
    assert "GENERATION_ACCEPTANCE_DOES_NOT_ACTIVATE_TRUST_STORE" in assessment["limitations"]
