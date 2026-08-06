from __future__ import annotations

from pathlib import Path

SELF = Path(__file__)
WORKFLOW = Path(".github/workflows/epic-05-supervisor-as-built-once.yml")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


epic = Path("docs/roadmap/epics/EPIC-05-runner-protocol-v2.md")
replace_once(epic, "| Document version | 1.7.1 |", "| Document version | 1.8.0 |")
replace_once(
    epic,
    "validated again on `main`. It uses the durable ledger for restart replay without connecting to\nreal capabilities or the legacy executor. Block 7 is now `IMPLEMENTING`: a repository-local POSIX\nprocess supervisor owns bounded process-group timeout, cancellation and residue cleanup but is\nnot connected to any adapter. `FINAL` remains false: production execution integration is\n`NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and bounded live\ncancellation has not been demonstrated through a Runner Protocol adapter.\n",
    "validated again on `main`. It uses the durable ledger for restart replay without connecting to\nreal capabilities or the legacy executor. The repository-local POSIX process supervisor was then\nintegrated through pull request [#117](https://github.com/pestoura/hermes-security-labs/pull/117)\nand validated again on `main`. It owns bounded process-group timeout, cancellation and residue\ncleanup but remains disconnected from every adapter. `FINAL` remains false: production execution\nintegration is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and\nbounded live cancellation has not been demonstrated through a Runner Protocol adapter.\n",
)
replace_once(
    epic,
    "### Block 7 — supervised process boundary (`IMPLEMENTING`)\n\n- Branch: `feat/epic-05-supervised-process-boundary`\n- SDK path: `platform/runner-protocol/src/runner_protocol_v2/supervision.py`\n- Documentation: `platform/runner-protocol/supervised-process-boundary.md`\n- Platform: POSIX process groups only\n- Invocation: absolute executable vector, `shell=False`, isolated standard input\n- Lifecycle: new session/process group, bounded output, `SIGTERM` then `SIGKILL`\n- Residue rule: surviving descendants prevent success and are actively cleaned\n- Cleanup failure: explicit `CLEANUP_FAILED`, never eligible for `PASS`\n- Adapter integration: `NOT_RUN`\n- Real capability execution: `NOT_RUN`\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nThe block must prove clean exit, hard timeout, external cancellation, forced termination,\ndescendant cleanup, output truncation and unsafe-specification refusal. It remains an execution\nprimitive rather than authorization, sandboxing, capability mapping or evidence handling.\n",
    "### Block 7 — supervised process boundary (`AS_BUILT`)\n\n- Branch: `feat/epic-05-supervised-process-boundary`\n- Pull request: [#117](https://github.com/pestoura/hermes-security-labs/pull/117)\n- Validated head: `daeaeb02c194fec776c981e8f0f6298fe3a03c1d`\n- Squash merge: `bf71fd7c6da2dcd2e179462677341a90f4f22b7a`\n- SDK path: `platform/runner-protocol/src/runner_protocol_v2/supervision.py`\n- Documentation: `platform/runner-protocol/supervised-process-boundary.md`\n- Platform: POSIX process groups only\n- Invocation: absolute executable vector, `shell=False`, isolated standard input\n- Lifecycle: new session/process group, bounded output, `SIGTERM` then `SIGKILL`\n- Residue rule: surviving descendants prevent success and are actively cleaned\n- Cleanup failure: explicit `CLEANUP_FAILED`, never eligible for `PASS`\n- Runner Protocol tests: 43 passed\n- Adapter integration: `NOT_RUN`\n- Real capability execution: `NOT_RUN`\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nThe merged block proves clean exit, hard timeout, external cancellation, forced termination,\ndescendant cleanup, output truncation and unsafe-specification refusal. It remains an execution\nprimitive rather than authorization, sandboxing, capability mapping or evidence handling.\n",
)
replace_once(
    epic,
    "  SDK --> LEDGER[Durable SQLite idempotency ledger]\n",
    "  SDK --> LEDGER[Durable SQLite idempotency ledger]\n  SDK --> SUP[POSIX process supervisor]\n",
)
replace_once(
    epic,
    "  VAL --> RUN[Future production runner adapter]\n",
    "  VAL --> RUN[Future production runner adapter]\n  SUP -. no adapter consumer .-> RUN\n",
)
replace_once(
    epic,
    "The delivered implementation is a repository-owned protocol contract and validation library.\nIt does not dispatch work and it has no process, network, container or laboratory side effects.\n",
    "The delivered implementation is a repository-owned protocol contract, validation library and\noptional local enforcement primitives for durable idempotency and POSIX process supervision. No\nrunner adapter dispatches work through the supervisor; its process side effects are limited to\ncontrolled repository tests and do not access networks, containers or laboratories.\n",
)
replace_once(
    epic,
    "| Production API execution integration | `NOT_RUN` |\n",
    "| Production API execution integration | `NOT_RUN` |\n| PR #117 validated head | `daeaeb02c194fec776c981e8f0f6298fe3a03c1d` |\n| Supervised-process merge SHA | `bf71fd7c6da2dcd2e179462677341a90f4f22b7a` |\n| PR #117 validate workflow | success — run `31093149197` |\n| PR #117 security/gitleaks workflow | success — run `31093149060` |\n| Post-merge supervisor validate workflow | success — run `31093252331` |\n| Post-merge supervisor security/gitleaks workflow | success — run `31093252418` |\n| Runner Protocol tests with supervisor | 43 passed |\n| Adapter consumption of supervisor | `NOT_RUN` |\n",
)
replace_once(
    epic,
    "### Epic-level criteria not yet met\n",
    "### Block 7 acceptance assessment\n\n| Criterion | Result | Evidence |\n| --- | --- | --- |\n| Absolute executable and working directory | met | negative specification tests |\n| Shell and pre-execution hooks absent | met | source/AST guard |\n| Process-group ownership | met | new-session implementation and descendant tests |\n| Hard timeout bounded and enforced | met | stubborn root/descendant timeout test |\n| External cancellation bounded and enforced | met | cancellation with `SIGTERM` to `SIGKILL` escalation |\n| Root exit with live descendant cannot pass | met | `RESIDUE_CLEANED` test |\n| Descendant residue removed before return | met | PID absence assertion |\n| Standard output and error bounded | met | independent truncation test |\n| Cleanup uncertainty fails closed | met by contract | `CLEANUP_FAILED` is never successful |\n| Runner Protocol adapter integration | `NOT_RUN` | no adapter imports or consumes the supervisor |\n| Sandbox and resource isolation | `NOT_RUN` | process groups do not provide containment |\n| Real capability execution | `NOT_RUN` | fixed synthetic test worker only |\n\n### Epic-level criteria not yet met\n",
)
replace_once(
    epic,
    "| Cancellation observable and bounded live | `NOT_RUN` | supervised process/cancellation integration tests |\n",
    "| Cancellation observable and bounded live | `PARTIAL` | local POSIX supervision is AS_BUILT; adapter-level protocol integration remains `NOT_RUN` |\n",
)
replace_once(
    epic,
    "- The first family-specific candidates are deliberately separate from the legacy API executor;\n  the durable variant proves restart replay only for synthetic effects. Production integration\n  requires a later capability-mapping and supervised execution block.\n",
    "- The first family-specific candidates are deliberately separate from the legacy API executor;\n  the durable variant proves restart replay only for synthetic effects.\n- The process supervisor was delivered as a reusable SDK primitive before adapter integration so\n  timeout and cancellation behaviour can be reviewed independently from capability mapping.\n  Production integration still requires a supervised synthetic adapter and later real capability\n  mapping under stronger sandbox and authorization controls.\n",
)
replace_once(
    epic,
    "- Cancellation and hard timeout are contract semantics only until supervised runtime support\n  is implemented.\n",
    "- Local cancellation, hard timeout and process-group cleanup are implemented in the SDK, but\n  no Runner Protocol adapter currently invokes the supervisor or translates its states into\n  protocol outcomes.\n",
)
replace_once(
    epic,
    "- External candidates require an additional sandbox boundary; the harness process boundary\n  alone is not a complete containment mechanism.\n",
    "- Process groups and the conformance harness require an additional sandbox boundary; neither\n  prevents session escape nor provides namespaces, cgroups, seccomp, network policy, privilege\n  separation or resource quotas.\n",
)
replace_once(
    epic,
    "| 2026-08-06 | 1.7.1 | Start supervised POSIX process boundary with adapter integration and real execution NOT_RUN. |\n",
    "| 2026-08-06 | 1.7.1 | Start supervised POSIX process boundary with adapter integration and real execution NOT_RUN. |\n| 2026-08-06 | 1.8.0 | Record supervised process boundary AS_BUILT with adapter integration and real execution NOT_RUN. |\n",
)

standalone = Path("platform/runner-protocol/supervised-process-boundary.md")
replace_once(
    standalone,
    "`IMPLEMENTING` — block 7 of `EPIC-05 — Runner Protocol v2`.\n",
    "`AS_BUILT` — block 7 of `EPIC-05 — Runner Protocol v2`, integrated through pull request\n[#117](https://github.com/pestoura/hermes-security-labs/pull/117).\n",
)
replace_once(
    standalone,
    "## Promotion boundary\n",
    "## Integrated evidence\n\n- Validated head: `daeaeb02c194fec776c981e8f0f6298fe3a03c1d`\n- Squash merge: `bf71fd7c6da2dcd2e179462677341a90f4f22b7a`\n- PR validate: `31093149197` — success\n- PR security/gitleaks: `31093149060` — success\n- Post-merge validate: `31093252331` — success\n- Post-merge security/gitleaks: `31093252418` — success\n- Runner Protocol suite: 43 passed\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nThe tests use only the fixed synthetic worker under `platform/runner-protocol/tests/fixtures/`.\nNo real capability, security tool, target, laboratory, Hermes or Kali MCP execution occurred.\n\n## Promotion boundary\n",
)

catalogue = Path("roadmap/epics/security-validation-platform-v2-concepts.yaml")
replace_once(
    catalogue,
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate and API durable synthetic restart replay. POSIX supervised-process boundary is IMPLEMENTING without adapter integration. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate, API durable synthetic restart replay and POSIX supervised-process boundary. No adapter consumes the supervisor. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
)

contracts = Path("docs/architecture/contracts/README.md")
replace_once(
    contracts,
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK and durable-ledger blocks `AS_BUILT`; API in-memory and durable synthetic candidates `AS_BUILT` / `PASS_SYNTHETIC`, production execution `NOT_RUN`; other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout or cancellation is a normalized non-success outcome |\n",
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK, durable ledger and POSIX process-supervision boundary `AS_BUILT`; API in-memory and durable synthetic candidates `AS_BUILT` / `PASS_SYNTHETIC`; no adapter consumes supervision and production execution is `NOT_RUN`; other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout, cancellation or verified cleanup is a normalized non-success outcome |\n",
)

SELF.unlink()
WORKFLOW.unlink()
