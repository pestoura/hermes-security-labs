from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    replace_once(path, marker, content + marker)


def main() -> None:
    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.5.0 |", "| Document version | 1.6.0 |")
    replace_once(
        epic,
        """`main`. The API-family synthetic-only candidate was subsequently integrated through pull
request [#111](https://github.com/pestoura/hermes-security-labs/pull/111) and validated
again on `main`. `FINAL` remains false: production execution integration is `NOT_RUN`,
promotion is blocked, and no runner family has demonstrated durable idempotent effects
or bounded live cancellation against real execution.
""",
        """`main`. The API-family synthetic-only candidate was subsequently integrated through pull
request [#111](https://github.com/pestoura/hermes-security-labs/pull/111) and validated
again on `main`. A reusable durable SQLite idempotency ledger was then integrated through
pull request [#113](https://github.com/pestoura/hermes-security-labs/pull/113) and validated
again on `main`. `FINAL` remains false: no runner consumes the durable ledger, production
execution integration is `NOT_RUN`, promotion is blocked, and bounded live cancellation
has not been demonstrated against real execution.
""",
    )
    replace_once(
        epic,
        "- Persistent replay-ledger storage and retention belong to runtime/Evidence Plane design.\n",
        "- Ledger retention, abandoned-claim reconciliation and adapter integration remain for later blocks.\n",
    )
    insert_before(
        epic,
        "## 15. As-built / final architecture\n",
        """### Block 5 — durable transactional idempotency ledger (`AS_BUILT`)

- Branch: `feat/epic-05-durable-idempotency-ledger`
- Pull request: [#113](https://github.com/pestoura/hermes-security-labs/pull/113)
- Validated head: `a9cafcba164dbf37dfd6a81e92b1be51d4e8ad51`
- Squash merge: `cc879b9fc5e20afcb8052c0f7197457c0ebcc86d`
- SDK class: `runner_protocol_v2.SQLiteIdempotencyLedger`
- Storage: caller-supplied SQLite database outside the repository
- Atomicity: `BEGIN IMMEDIATE`, unique idempotency key and immutable completion
- Durability: WAL, `synchronous=FULL`, schema version and integrity check
- Classifications: `NEW`, `IN_PROGRESS`, `REPLAY_SAME`, `IDEMPOTENCY_CONFLICT`
- Abandoned `IN_PROGRESS` reclaim: disabled; reconciliation required
- Runner adapter integration: `NOT_RUN`
- Runtime declaration: `NO_RUNTIME_CHANGE`

The merged ledger proves a single winning concurrent claim, persistence across reopen,
terminal replay without a second effect decision, immutable fingerprint/outcome handling and
fail-closed corrupt or unknown state. It is an enforcement component, not authorization and
not evidence that any real runner is idempotent.

""",
    )
    replace_once(
        epic,
        "  SDK --> IDEM[Fingerprint and idempotency classification]\n",
        "  SDK --> IDEM[Fingerprint and idempotency classification]\n"
        "  SDK --> LEDGER[Durable SQLite idempotency ledger]\n",
    )
    replace_once(
        epic,
        "| API promotion status | blocked |\n",
        """| API promotion status | blocked |
| PR #113 validated head | `a9cafcba164dbf37dfd6a81e92b1be51d4e8ad51` |
| Durable-ledger merge SHA | `cc879b9fc5e20afcb8052c0f7197457c0ebcc86d` |
| PR #113 validate workflow | success — run `31088913223` |
| PR #113 security/gitleaks workflow | success — run `31088912202` |
| Post-merge ledger validate workflow | success — run `31089022988` |
| Post-merge ledger security/gitleaks workflow | success — run `31089022565` |
| Runner Protocol tests with ledger | 36 passed |
| Concurrent claim winners | exactly one `NEW` |
| Adapter integration with durable ledger | `NOT_RUN` |
""",
    )
    insert_before(
        epic,
        "### Epic-level criteria not yet met\n",
        """### Block 5 acceptance assessment

| Criterion | Result | Evidence |
| --- | --- | --- |
| Atomic claim under concurrency | met | 16 concurrent claims yield one `NEW` |
| Same fingerprint during active claim | met | classified `IN_PROGRESS`; no second dispatch decision |
| Changed fingerprint under same key | met | `IDEMPOTENCY_CONFLICT` |
| Terminal outcome survives reopen | met | SQLite close/reopen and `REPLAY_SAME` test |
| Completed identity and outcome immutable | met | conflicting completion tests |
| Invalid/corrupt/unknown state fails closed | met | negative database and schema-version tests |
| Automatic reclaim of uncertain effects | deliberately absent | abandoned `IN_PROGRESS` requires reconciliation |
| Real runner effect deduplication | `NOT_RUN` | no adapter consumes the ledger |

""",
    )
    replace_once(
        epic,
        "| Same idempotency key never duplicates effects | `NOT_RUN` | persistent ledger and effect-level replay tests |",
        "| Same idempotency key never duplicates effects | `PARTIAL` | durable ledger is AS_BUILT; adapter effect-level integration remains `NOT_RUN` |",
    )
    replace_once(
        epic,
        """- The block introduced deterministic fingerprint classification but deliberately did not
  implement a persistent replay ledger.
""",
        """- Deterministic fingerprint classification was delivered first; block 5 subsequently added
  a durable transactional ledger without connecting it to any execution adapter.
""",
    )
    replace_once(
        epic,
        """- Fingerprint classification does not itself prevent duplicate effects without a persistent,
  atomic idempotency ledger.
""",
        """- A durable atomic ledger now exists, but it does not prevent duplicate real effects until each
  adapter claims before execution and persists the terminal outcome after effect completion.
""",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.5.0 | Record API synthetic candidate AS_BUILT with PASS_SYNTHETIC evidence, execution NOT_RUN and promotion blocked. |",
        "| 2026-08-06 | 1.5.0 | Record API synthetic candidate AS_BUILT with PASS_SYNTHETIC evidence, execution NOT_RUN and promotion blocked. |\n"
        "| 2026-08-06 | 1.6.0 | Record durable transactional idempotency ledger AS_BUILT with adapter integration NOT_RUN. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_once(
        concepts,
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK and API synthetic-candidate blocks. The API candidate has PASS_SYNTHETIC with execution integration NOT_RUN and promotion blocked; DevSecOps and AI/MCP remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK, API synthetic candidate and durable idempotency-ledger blocks. API execution and durable-ledger adapter integration remain NOT_RUN; promotion is blocked; DevSecOps and AI/MCP remain NOT_RUN."\n',
    )

    contracts = "docs/architecture/contracts/README.md"
    replace_once(
        contracts,
        "contract, conformance-kit and SDK blocks `AS_BUILT`; API synthetic candidate `AS_BUILT` / `PASS_SYNTHETIC`, execution `NOT_RUN`; other adapters `NOT_RUN`;",
        "contract, conformance-kit, SDK and durable-ledger blocks `AS_BUILT`; API synthetic candidate `AS_BUILT` / `PASS_SYNTHETIC`, execution and ledger integration `NOT_RUN`; other adapters `NOT_RUN`;",
    )

    ledger_doc = "platform/runner-protocol/durable-idempotency-ledger.md"
    replace_once(
        ledger_doc,
        "`IMPLEMENTING` — block 5 of `EPIC-05 — Runner Protocol v2`.\n",
        "`AS_BUILT` — block 5 of `EPIC-05 — Runner Protocol v2`, integrated through PR #113 at `cc879b9fc5e20afcb8052c0f7197457c0ebcc86d`.\n",
    )
    replace_once(
        ledger_doc,
        "## Explicit non-goals\n",
        """## As-built evidence

- validated head: `a9cafcba164dbf37dfd6a81e92b1be51d4e8ad51`;
- squash merge: `cc879b9fc5e20afcb8052c0f7197457c0ebcc86d`;
- PR validate: `31088913223` — success;
- PR security/gitleaks: `31088912202` — success;
- post-merge validate: `31089022988` — success;
- post-merge security/gitleaks: `31089022565` — success;
- Runner Protocol tests: 36 passed;
- runtime validation: `NOT_APPLICABLE` — `NO_RUNTIME_CHANGE`.

## Explicit non-goals
""",
    )

    readme = "platform/runner-protocol/README.md"
    replace_once(
        readme,
        "Current implementation state: contract, repository-local SDK and vendor-neutral conformance kit are available; an API-family candidate passes synthetic conformance only, while real execution integration for API, DevSecOps and AI/MCP remains unimplemented.",
        "Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; an API-family candidate passes synthetic conformance only, while durable-ledger adapter integration and real execution for API, DevSecOps and AI/MCP remain unimplemented.",
    )
    replace_once(
        readme,
        "The SDK is side-effect free: it does not dispatch, authorize, cancel or execute work. It is a\nshared dependency for future adapters so validation and fingerprint semantics are not copied or\nreinterpreted per runner family.\n",
        "The SDK does not dispatch, authorize, cancel or execute work. Its validation functions are\nside-effect free; the optional [`SQLiteIdempotencyLedger`](durable-idempotency-ledger.md) persists\nonly caller-supplied idempotency state and validated terminal outcomes. No adapter uses the ledger\nyet. The SDK remains the shared dependency so protocol semantics are not copied per family.\n",
    )
    replace_once(
        readme,
        "- [`src/runner_protocol_v2/`](src/runner_protocol_v2/)\n",
        "- [`src/runner_protocol_v2/`](src/runner_protocol_v2/)\n"
        "- [`src/runner_protocol_v2/idempotency.py`](src/runner_protocol_v2/idempotency.py)\n"
        "- [`durable-idempotency-ledger.md`](durable-idempotency-ledger.md)\n",
    )
    replace_once(
        readme,
        "- no live cancellation, process termination or replay cache;\n",
        "- no live cancellation or process termination;\n- no adapter integration of the durable idempotency ledger;\n",
    )

    for temporary in (
        ".github/workflows/epic-05-ledger-as-built-once.yml",
        "tools/tmp_epic05_ledger_as_built_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
