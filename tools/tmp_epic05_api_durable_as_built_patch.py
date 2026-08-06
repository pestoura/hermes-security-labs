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
    replace_once(epic, "| Document version | 1.6.1 |", "| Document version | 1.7.0 |")
    replace_once(
        epic,
        """again on `main`. Block 6 is now `IMPLEMENTING`: a separate API-family synthetic candidate
uses the durable ledger for restart replay without connecting to real capabilities or the legacy
executor. `FINAL` remains false: production execution integration is `NOT_RUN`, promotion is
blocked, and bounded live cancellation has not been demonstrated against real execution.
""",
        """again on `main`. A separate API-family durable synthetic candidate was then integrated
through pull request [#115](https://github.com/pestoura/hermes-security-labs/pull/115) and
validated again on `main`. It uses the durable ledger for restart replay without connecting to
real capabilities or the legacy executor. `FINAL` remains false: production execution integration
is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and bounded live
cancellation has not been demonstrated against real execution.
""",
    )
    replace_once(
        epic,
        "### Block 6 — API durable synthetic integration (`IMPLEMENTING`)\n",
        "### Block 6 — API durable synthetic integration (`AS_BUILT`)\n",
    )
    replace_once(
        epic,
        """- Branch: `feat/epic-05-api-durable-ledger-integration`
- Candidate path: `security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`
""",
        """- Branch: `feat/epic-05-api-durable-ledger-integration`
- Pull request: [#115](https://github.com/pestoura/hermes-security-labs/pull/115)
- Validated head: `dc08ff3779ef47fd48846efc6149b022617b107e`
- Squash merge: `3ff427e4c5122f0733bc04c9291acfdfc28b1448`
- Candidate path: `security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`
""",
    )
    replace_once(
        epic,
        """The block must pass the vendor-neutral conformance kit with disposable durable state and prove
that restart replay does not increase the synthetic effect counter. This remains synthetic
effect-level evidence only.
""",
        """The merged block passes the vendor-neutral conformance kit with disposable durable state and
proves that restart replay does not increase the synthetic effect counter. It also persists and
replays cancellation outcomes, refuses changed or uncertain effects, and fails closed when the
terminal outcome cannot be committed. This remains synthetic effect-level evidence only.
""",
    )
    replace_once(
        epic,
        "  VAL --> API[API synthetic-only candidate]\n",
        "  VAL --> API[API in-memory synthetic candidate]\n"
        "  VAL --> DAPI[API durable synthetic candidate]\n"
        "  DAPI --> LEDGER\n",
    )
    replace_once(
        epic,
        "  KIT --> REPORT[Sanitized conformance report]\n",
        "  KIT --> DAPI\n  KIT --> REPORT[Sanitized conformance report]\n",
    )
    replace_once(
        epic,
        "| Adapter integration with durable ledger | `NOT_RUN` |\n",
        """| Adapter integration with durable ledger | synthetic API integration `AS_BUILT`; production `NOT_RUN` |
| PR #115 validated head | `dc08ff3779ef47fd48846efc6149b022617b107e` |
| API durable synthetic merge SHA | `3ff427e4c5122f0733bc04c9291acfdfc28b1448` |
| PR #115 validate workflow | success — run `31090758807` |
| PR #115 security/gitleaks workflow | success — run `31090759705` |
| Post-merge durable API validate workflow | success — run `31090875891` |
| Post-merge durable API security/gitleaks workflow | success — run `31090875979` |
| Directed protocol/API/roadmap/docs tests | 929 passed |
| Durable restart replay | `PASS_SYNTHETIC`; no second synthetic effect |
| Production API execution integration | `NOT_RUN` |
""",
    )
    insert_before(
        epic,
        "### Epic-level criteria not yet met\n",
        """### Block 6 acceptance assessment

| Criterion | Result | Evidence |
| --- | --- | --- |
| Durable claim precedes synthetic effect | met | candidate control flow and tests |
| Restart replay avoids second synthetic effect | met | new candidate instance; effect counter remains zero |
| Retry correlation is reconstructed | met | replay carries current `attempt_id` |
| Changed effect under the same key is refused | met | restart conflict test |
| Uncertain `IN_PROGRESS` is not reclaimed | met | restart refusal and persisted active state |
| Cancellation outcome persists and replays | met | same-process cancellation plus restart replay |
| Completion failure fails closed | met | non-retryable `INCONCLUSIVE` test |
| Real capability and authorization create no claim | met | negative ledger-record tests |
| Production API effect deduplication | `NOT_RUN` | no real capability mapping or executor integration |
| Live bounded process cancellation | `NOT_RUN` | synthetic protocol cancellation only |

""",
    )
    replace_once(
        epic,
        "| Same idempotency key never duplicates effects | `PARTIAL` | durable ledger is AS_BUILT; adapter effect-level integration remains `NOT_RUN` |",
        "| Same idempotency key never duplicates effects | `PARTIAL` | synthetic API restart replay is AS_BUILT; production adapter effect-level integration remains `NOT_RUN` |",
    )
    replace_once(
        epic,
        """- The first family-specific candidate is deliberately separate from the legacy API executor;
  production integration requires a later capability-mapping and supervised execution block.
""",
        """- The first family-specific candidates are deliberately separate from the legacy API executor;
  the durable variant proves restart replay only for synthetic effects. Production integration
  requires a later capability-mapping and supervised execution block.
""",
    )
    replace_once(
        epic,
        """- A durable atomic ledger now exists, but it does not prevent duplicate real effects until each
  adapter claims before execution and persists the terminal outcome after effect completion.
""",
        """- The API durable synthetic candidate now consumes the atomic ledger, but duplicate real effects
  remain possible until production adapters claim before execution and persist the terminal outcome.
""",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.6.1 | Start API durable synthetic integration with restart replay and production execution blocked. |",
        "| 2026-08-06 | 1.6.1 | Start API durable synthetic integration with restart replay and production execution blocked. |\n"
        "| 2026-08-06 | 1.7.0 | Record API durable synthetic restart replay AS_BUILT with production execution NOT_RUN and promotion blocked. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_once(
        concepts,
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK, API synthetic candidate and durable ledger; API durable synthetic restart-replay integration is IMPLEMENTING. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate and API durable synthetic restart replay. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    )

    contracts = "docs/architecture/contracts/README.md"
    replace_once(
        contracts,
        "contract, conformance-kit, SDK and durable-ledger blocks `AS_BUILT`; API synthetic candidate `AS_BUILT` / `PASS_SYNTHETIC`, execution and ledger integration `NOT_RUN`; other adapters `NOT_RUN`;",
        "contract, conformance-kit, SDK and durable-ledger blocks `AS_BUILT`; API in-memory and durable synthetic candidates `AS_BUILT` / `PASS_SYNTHETIC`, production execution `NOT_RUN`; other adapters `NOT_RUN`;",
    )

    candidate_doc = "security/packs/api/docs/runner-protocol-durable-candidate.md"
    replace_once(
        candidate_doc,
        "`IMPLEMENTING` — block 6 of `EPIC-05 — Runner Protocol v2`.\n",
        "`AS_BUILT` — block 6 of `EPIC-05 — Runner Protocol v2`, integrated through PR #115 at `3ff427e4c5122f0733bc04c9291acfdfc28b1448`.\n",
    )
    insert_before(
        candidate_doc,
        "## Explicit non-goals\n",
        """## As-built evidence

- validated head: `dc08ff3779ef47fd48846efc6149b022617b107e`;
- squash merge: `3ff427e4c5122f0733bc04c9291acfdfc28b1448`;
- directed protocol/API/roadmap/docs suite: 929 passed;
- PR validate: `31090758807` — success;
- PR security/gitleaks: `31090759705` — success;
- post-merge validate: `31090875891` — success;
- post-merge security/gitleaks: `31090875979` — success;
- vendor-neutral conformance: `PASS_SYNTHETIC`;
- production execution integration: `NOT_RUN`;
- runtime validation: `NOT_APPLICABLE` — `NO_RUNTIME_CHANGE`.

## Explicit non-goals
""",
    )

    for temporary in (
        ".github/workflows/epic-05-api-durable-as-built-once.yml",
        "tools/tmp_epic05_api_durable_as_built_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
