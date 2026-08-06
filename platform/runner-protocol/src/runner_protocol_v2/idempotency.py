"""Durable fail-closed idempotency ledger for Runner Protocol v2."""

from __future__ import annotations

import json
import os
import sqlite3
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .contracts import ProtocolValidationError, validate_semantics

SCHEMA_VERSION = 1
_ALLOWED_STATES = frozenset({"IN_PROGRESS", "COMPLETED"})
_HEX = frozenset(string.hexdigits.lower())


class LedgerError(RuntimeError):
    """Base error for durable idempotency state."""


class LedgerUnavailableError(LedgerError):
    """The ledger cannot be trusted or accessed safely."""


class LedgerConflictError(LedgerError):
    """The requested transition conflicts with immutable ledger state."""


class LedgerStateError(LedgerError):
    """The requested transition is invalid for the current state."""


@dataclass(frozen=True)
class LedgerRecord:
    """One immutable idempotency identity and its optional terminal outcome."""

    idempotency_key: str
    fingerprint: str
    state: Literal["IN_PROGRESS", "COMPLETED"]
    outcome: dict[str, Any] | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LedgerDecision:
    """Result of an atomic claim or completion operation."""

    classification: Literal[
        "NEW",
        "IN_PROGRESS",
        "REPLAY_SAME",
        "IDEMPOTENCY_CONFLICT",
        "COMPLETED",
    ]
    record: LedgerRecord | None = None


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _validate_key(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise LedgerStateError("idempotency key must contain 1 to 256 characters")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise LedgerStateError("idempotency key contains disallowed whitespace")
    return value


def _validate_fingerprint(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in _HEX for character in value)
    ):
        raise LedgerStateError(
            "fingerprint must be a lowercase SHA-256 hexadecimal digest"
        )
    return value


def _canonical_outcome(outcome: dict[str, Any]) -> str:
    if not isinstance(outcome, dict) or outcome.get("message_type") != "runner.outcome":
        raise LedgerStateError("only a Runner Protocol terminal outcome can be persisted")
    validate_semantics(outcome)
    return json.dumps(outcome, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class SQLiteIdempotencyLedger:
    """SQLite-backed ledger with atomic claim and completion semantics."""

    def __init__(self, database_path: str | os.PathLike[str]):
        self.database_path = Path(database_path)
        self._validate_path()
        self._initialize()

    def _validate_path(self) -> None:
        if str(self.database_path) == ":memory:":
            raise LedgerUnavailableError("durable ledger cannot use an in-memory database")
        parent = self.database_path.parent
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise LedgerUnavailableError("ledger parent directory is unavailable")
        if self.database_path.is_symlink():
            raise LedgerUnavailableError("ledger database path cannot be a symbolic link")
        if self.database_path.exists() and not self.database_path.is_file():
            raise LedgerUnavailableError("ledger database path is not a regular file")

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=5.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except sqlite3.Error as exc:
            raise LedgerUnavailableError("idempotency ledger is unavailable") from exc

    def _initialize(self) -> None:
        created = not self.database_path.exists()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, SCHEMA_VERSION}:
                raise LedgerUnavailableError(
                    "unsupported idempotency ledger schema version"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('IN_PROGRESS', 'COMPLETED')),
                    outcome_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (state = 'IN_PROGRESS' AND outcome_json IS NULL)
                        OR (state = 'COMPLETED' AND outcome_json IS NOT NULL)
                    )
                )
                """
            )
            columns = [
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(idempotency_records)"
                ).fetchall()
            ]
            expected = [
                "idempotency_key",
                "fingerprint",
                "state",
                "outcome_json",
                "created_at",
                "updated_at",
            ]
            if columns != expected:
                raise LedgerUnavailableError("idempotency ledger schema is inconsistent")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
            check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise LedgerUnavailableError("idempotency ledger integrity check failed")
        except LedgerError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise LedgerUnavailableError(
                "idempotency ledger initialization failed"
            ) from exc
        finally:
            if connection is not None:
                connection.close()
        if created:
            try:
                self.database_path.chmod(0o600)
            except OSError as exc:
                raise LedgerUnavailableError(
                    "idempotency ledger permissions could not be secured"
                ) from exc

    @staticmethod
    def _record(row: sqlite3.Row) -> LedgerRecord:
        state = row["state"]
        if state not in _ALLOWED_STATES:
            raise LedgerUnavailableError("idempotency ledger contains an invalid state")
        outcome: dict[str, Any] | None = None
        if state == "COMPLETED":
            try:
                loaded = json.loads(row["outcome_json"])
                if not isinstance(loaded, dict):
                    raise TypeError("outcome is not an object")
                _canonical_outcome(loaded)
            except (
                TypeError,
                json.JSONDecodeError,
                LedgerStateError,
                ProtocolValidationError,
            ) as exc:
                raise LedgerUnavailableError(
                    "idempotency ledger contains an invalid outcome"
                ) from exc
            outcome = loaded
        elif row["outcome_json"] is not None:
            raise LedgerUnavailableError(
                "in-progress idempotency record contains a terminal outcome"
            )
        return LedgerRecord(
            idempotency_key=row["idempotency_key"],
            fingerprint=row["fingerprint"],
            state=state,
            outcome=outcome,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def claim(
        self,
        idempotency_key: str,
        fingerprint: str,
        *,
        now: str | None = None,
    ) -> LedgerDecision:
        """Atomically claim an idempotency key or classify its existing state."""
        key = _validate_key(idempotency_key)
        digest = _validate_fingerprint(fingerprint)
        timestamp = now or _utc_now()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO idempotency_records (
                        idempotency_key, fingerprint, state, outcome_json,
                        created_at, updated_at
                    ) VALUES (?, ?, 'IN_PROGRESS', NULL, ?, ?)
                    """,
                    (key, digest, timestamp, timestamp),
                )
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                    (key,),
                ).fetchone()
                connection.commit()
                return LedgerDecision("NEW", self._record(row))

            record = self._record(row)
            if record.fingerprint != digest:
                connection.commit()
                return LedgerDecision("IDEMPOTENCY_CONFLICT", record)
            if record.state == "IN_PROGRESS":
                connection.commit()
                return LedgerDecision("IN_PROGRESS", record)
            connection.commit()
            return LedgerDecision("REPLAY_SAME", record)
        except LedgerError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise LedgerUnavailableError("idempotency claim failed safely") from exc
        finally:
            if connection is not None:
                connection.close()

    def complete(
        self,
        idempotency_key: str,
        fingerprint: str,
        outcome: dict[str, Any],
        *,
        now: str | None = None,
    ) -> LedgerDecision:
        """Persist one immutable terminal outcome after a successful claim."""
        key = _validate_key(idempotency_key)
        digest = _validate_fingerprint(fingerprint)
        outcome_json = _canonical_outcome(outcome)
        timestamp = now or _utc_now()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                raise LedgerStateError(
                    "terminal outcome cannot be recorded before an atomic claim"
                )
            record = self._record(row)
            if record.fingerprint != digest:
                raise LedgerConflictError(
                    "terminal outcome fingerprint conflicts with the claimed effect"
                )
            if record.state == "COMPLETED":
                existing_json = _canonical_outcome(record.outcome or {})
                if existing_json != outcome_json:
                    raise LedgerConflictError("completed idempotency record is immutable")
                connection.commit()
                return LedgerDecision("REPLAY_SAME", record)

            cursor = connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'COMPLETED', outcome_json = ?, updated_at = ?
                WHERE idempotency_key = ? AND fingerprint = ? AND state = 'IN_PROGRESS'
                """,
                (outcome_json, timestamp, key, digest),
            )
            if cursor.rowcount != 1:
                raise LedgerStateError(
                    "idempotency completion transition was not applied"
                )
            row = connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            connection.commit()
            return LedgerDecision("COMPLETED", self._record(row))
        except LedgerError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise LedgerUnavailableError("idempotency completion failed safely") from exc
        finally:
            if connection is not None:
                connection.close()

    def get(self, idempotency_key: str) -> LedgerRecord | None:
        """Read one record without changing its state."""
        key = _validate_key(idempotency_key)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            row = connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            return None if row is None else self._record(row)
        except LedgerError:
            raise
        except sqlite3.Error as exc:
            raise LedgerUnavailableError("idempotency read failed safely") from exc
        finally:
            if connection is not None:
                connection.close()

    def count(self) -> int:
        """Return the number of trusted records without changing ledger state."""
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            row = connection.execute(
                "SELECT COUNT(*) AS record_count FROM idempotency_records"
            ).fetchone()
            if row is None:
                raise LedgerUnavailableError("idempotency count returned no result")
            count = row["record_count"]
            if not isinstance(count, int) or count < 0:
                raise LedgerUnavailableError(
                    "idempotency count returned an invalid result"
                )
            return count
        except LedgerError:
            raise
        except sqlite3.Error as exc:
            raise LedgerUnavailableError("idempotency count failed safely") from exc
        finally:
            if connection is not None:
                connection.close()
