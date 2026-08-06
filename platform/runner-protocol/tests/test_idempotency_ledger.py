from __future__ import annotations

import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from runner_protocol_v2 import (
    LedgerConflictError,
    LedgerStateError,
    LedgerUnavailableError,
    SQLiteIdempotencyLedger,
)

KEY = "runner-protocol:test:0001"
FINGERPRINT = "a" * 64
OTHER_FINGERPRINT = "b" * 64
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def terminal_outcome() -> dict:
    return {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-06T09:20:01Z",
        "status": "PASS",
        "started_at": "2026-08-06T09:20:00Z",
        "finished_at": "2026-08-06T09:20:01Z",
        "output": {"result": "synthetic-ledger-success"},
        "evidence_refs": [
            {
                "evidence_id": "55555555-5555-4555-8555-555555555555",
                "kind": "protocol",
                "classification": "INTERNAL",
                "sha256": "c" * 64,
                "uri": "evidence://runner-protocol/ledger-test",
            }
        ],
    }


def ledger(tmp_path: Path) -> SQLiteIdempotencyLedger:
    return SQLiteIdempotencyLedger(tmp_path / "idempotency.sqlite3")


def test_atomic_claim_classifies_new_in_progress_and_conflict(tmp_path: Path) -> None:
    store = ledger(tmp_path)

    first = store.claim(KEY, FINGERPRINT, now="2026-08-06T09:20:00Z")
    assert first.classification == "NEW"
    assert first.record is not None
    assert first.record.state == "IN_PROGRESS"

    duplicate = store.claim(KEY, FINGERPRINT)
    assert duplicate.classification == "IN_PROGRESS"
    assert duplicate.record == first.record

    conflict = store.claim(KEY, OTHER_FINGERPRINT)
    assert conflict.classification == "IDEMPOTENCY_CONFLICT"
    assert conflict.record is not None
    assert conflict.record.fingerprint == FINGERPRINT


def test_completed_outcome_survives_reopen_and_replays(tmp_path: Path) -> None:
    database = tmp_path / "idempotency.sqlite3"
    first_process = SQLiteIdempotencyLedger(database)
    first_process.claim(KEY, FINGERPRINT)
    completed = first_process.complete(KEY, FINGERPRINT, terminal_outcome())

    assert completed.classification == "COMPLETED"
    assert completed.record is not None
    assert completed.record.state == "COMPLETED"

    reopened = SQLiteIdempotencyLedger(database)
    replay = reopened.claim(KEY, FINGERPRINT)
    assert replay.classification == "REPLAY_SAME"
    assert replay.record is not None
    assert replay.record.outcome == terminal_outcome()

    repeated_completion = reopened.complete(KEY, FINGERPRINT, terminal_outcome())
    assert repeated_completion.classification == "REPLAY_SAME"


def test_concurrent_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    store = ledger(tmp_path)

    def claim() -> str:
        return store.claim(KEY, FINGERPRINT).classification

    with ThreadPoolExecutor(max_workers=8) as executor:
        classifications = list(executor.map(lambda _: claim(), range(16)))

    assert classifications.count("NEW") == 1
    assert classifications.count("IN_PROGRESS") == 15


def test_completion_requires_claim_and_immutable_identity(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    with pytest.raises(LedgerStateError, match="before an atomic claim"):
        store.complete(KEY, FINGERPRINT, terminal_outcome())

    store.claim(KEY, FINGERPRINT)
    with pytest.raises(LedgerConflictError, match="fingerprint"):
        store.complete(KEY, OTHER_FINGERPRINT, terminal_outcome())

    store.complete(KEY, FINGERPRINT, terminal_outcome())
    changed = terminal_outcome()
    changed["output"] = {"result": "changed"}
    with pytest.raises(LedgerConflictError, match="immutable"):
        store.complete(KEY, FINGERPRINT, changed)


def test_invalid_key_fingerprint_and_outcome_fail_closed(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    with pytest.raises(LedgerStateError, match="idempotency key"):
        store.claim(" bad-key ", FINGERPRINT)
    with pytest.raises(LedgerStateError, match="SHA-256"):
        store.claim(KEY, "not-a-digest")

    store.claim(KEY, FINGERPRINT)
    invalid = terminal_outcome()
    invalid["evidence_refs"] = []
    with pytest.raises(Exception):
        store.complete(KEY, FINGERPRINT, invalid)


def test_corrupt_and_unknown_schema_are_unavailable(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(LedgerUnavailableError):
        SQLiteIdempotencyLedger(corrupt)

    future = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(future)
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(LedgerUnavailableError, match="schema version"):
        SQLiteIdempotencyLedger(future)


def test_database_permissions_are_owner_only(tmp_path: Path) -> None:
    database = tmp_path / "idempotency.sqlite3"
    SQLiteIdempotencyLedger(database)
    assert database.stat().st_mode & 0o077 == 0


def test_in_memory_and_symlink_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(LedgerUnavailableError, match="in-memory"):
        SQLiteIdempotencyLedger(":memory:")

    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "ledger-link.sqlite3"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    with pytest.raises(LedgerUnavailableError, match="symbolic link"):
        SQLiteIdempotencyLedger(link)
