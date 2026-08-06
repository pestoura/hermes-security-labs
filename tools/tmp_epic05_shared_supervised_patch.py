from __future__ import annotations

from pathlib import Path

SELF = Path(__file__)
WORKFLOW = Path(".github/workflows/epic-05-shared-supervised-once.yml")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


ledger = Path("platform/runner-protocol/src/runner_protocol_v2/idempotency.py")
replace_once(
    ledger,
    "        finally:\n            if connection is not None:\n                connection.close()\n",
    "        finally:\n            if connection is not None:\n                connection.close()\n\n    def count(self) -> int:\n        \"\"\"Return the number of trusted records without changing ledger state.\"\"\"\n        connection: sqlite3.Connection | None = None\n        try:\n            connection = self._connect()\n            row = connection.execute(\n                \"SELECT COUNT(*) AS record_count FROM idempotency_records\"\n            ).fetchone()\n            if row is None:\n                raise LedgerUnavailableError(\n                    \"idempotency count returned no result\"\n                )\n            count = row[\"record_count\"]\n            if not isinstance(count, int) or count < 0:\n                raise LedgerUnavailableError(\n                    \"idempotency count returned an invalid result\"\n                )\n            return count\n        except LedgerError:\n            raise\n        except sqlite3.Error as exc:\n            raise LedgerUnavailableError(\n                \"idempotency count failed safely\"\n            ) from exc\n        finally:\n            if connection is not None:\n                connection.close()\n",
)

ledger_tests = Path("platform/runner-protocol/tests/test_idempotency_ledger.py")
text = ledger_tests.read_text(encoding="utf-8")
addition = """


def test_count_is_consistent_across_claim_completion_and_reopen(tmp_path: Path) -> None:
    database = tmp_path / "idempotency.sqlite3"
    store = SQLiteIdempotencyLedger(database)
    assert store.count() == 0

    store.claim(KEY, FINGERPRINT)
    assert store.count() == 1
    store.complete(KEY, FINGERPRINT, terminal_outcome())
    assert store.count() == 1

    reopened = SQLiteIdempotencyLedger(database)
    assert reopened.count() == 1
"""
if "def test_count_is_consistent_across_claim_completion_and_reopen" in text:
    raise RuntimeError("count test already present")
ledger_tests.write_text(text + addition, encoding="utf-8")

for wrapper in (
    Path("security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py"),
    Path("security/packs/devsecops/src/devsecops_runbooks/supervised_runner_protocol_adapter.py"),
):
    text = wrapper.read_text(encoding="utf-8")
    old = """        kwargs = {
            "family": "api",
            "worker_path": WORKER,
            "durable_ledger": durable_ledger,
            "working_directory": working_directory,
        }
        if supervisor is not None:
            kwargs["supervisor"] = supervisor
        super().__init__(**kwargs)  # type: ignore[arg-type]
"""
    family = "api"
    if old not in text:
        old = """        kwargs = {
            "family": "devsecops",
            "worker_path": WORKER,
            "durable_ledger": durable_ledger,
            "working_directory": working_directory,
        }
        if supervisor is not None:
            kwargs["supervisor"] = supervisor
        super().__init__(**kwargs)  # type: ignore[arg-type]
"""
        family = "devsecops"
    if old not in text:
        raise RuntimeError(f"wrapper initializer not found: {wrapper}")
    new = f"""        if supervisor is None:
            super().__init__(
                family="{family}",
                worker_path=WORKER,
                durable_ledger=durable_ledger,
                working_directory=working_directory,
            )
        else:
            super().__init__(
                family="{family}",
                worker_path=WORKER,
                durable_ledger=durable_ledger,
                working_directory=working_directory,
                supervisor=supervisor,
            )
"""
    wrapper.write_text(text.replace(old, new, 1), encoding="utf-8")

SELF.unlink()
WORKFLOW.unlink()
