from __future__ import annotations

from pathlib import Path

BRANCH_WORKFLOW = Path(".github/workflows/epic-05-supervisor-docs-once.yml")
SELF = Path(__file__)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


readme = Path("platform/runner-protocol/README.md")
replace_once(
    readme,
    "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; API-family in-memory and durable candidates pass synthetic conformance only, while real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
    "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; API-family in-memory and durable candidates pass synthetic conformance only; a POSIX supervised-process boundary is implementing with no adapter integration, while real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
)
replace_once(
    readme,
    "The SDK does not dispatch, authorize, cancel or execute work. Its validation functions are\nside-effect free; the optional [`SQLiteIdempotencyLedger`](durable-idempotency-ledger.md) persists\nonly caller-supplied idempotency state and validated terminal outcomes. The API durable synthetic\ncandidate uses it solely for conformance and restart-replay tests. The SDK remains the shared\ndependency so protocol semantics are not copied per family.\n",
    "The SDK validation functions remain side-effect free. The optional\n[`SQLiteIdempotencyLedger`](durable-idempotency-ledger.md) persists only caller-supplied\nidempotency state and validated terminal outcomes. The optional\n[`PosixProcessSupervisor`](supervised-process-boundary.md) is an execution primitive that starts\nonly an absolute executable without a shell and owns bounded process-group cleanup. It does not\nauthorize, select capabilities, map targets or produce protocol evidence. No existing adapter\nconsumes it. The SDK remains the shared dependency so protocol and lifecycle semantics are not\ncopied per family.\n",
)
replace_once(
    readme,
    "## Conformance kit\n",
    "## Supervised process boundary\n\nThe repository-local SDK includes the `PosixProcessSupervisor` described in\n[`supervised-process-boundary.md`](supervised-process-boundary.md). It validates an absolute\nexecutable and working directory, invokes without a shell, creates a new process group, captures\nbounded output, escalates `SIGTERM` to `SIGKILL`, and refuses to classify root exit as success\nwhile descendants remain. `CLEANUP_FAILED` is never eligible for protocol `PASS`.\n\nThis is not a sandbox. It provides no cgroup, namespace, seccomp, network, privilege or resource\nquota enforcement and is not connected to any runner adapter. Real capability execution remains\n`NOT_RUN`.\n\n## Conformance kit\n",
)
replace_once(
    readme,
    "- [`src/runner_protocol_v2/idempotency.py`](src/runner_protocol_v2/idempotency.py)\n- [`durable-idempotency-ledger.md`](durable-idempotency-ledger.md)\n",
    "- [`src/runner_protocol_v2/idempotency.py`](src/runner_protocol_v2/idempotency.py)\n- [`src/runner_protocol_v2/supervision.py`](src/runner_protocol_v2/supervision.py)\n- [`durable-idempotency-ledger.md`](durable-idempotency-ledger.md)\n- [`supervised-process-boundary.md`](supervised-process-boundary.md)\n",
)
replace_once(
    readme,
    "- [`tests/test_sdk.py`](tests/test_sdk.py)\n",
    "- [`tests/test_sdk.py`](tests/test_sdk.py)\n- [`tests/test_supervision.py`](tests/test_supervision.py)\n",
)
replace_once(
    readme,
    "- no live cancellation or process termination;\n",
    "- no adapter-level live cancellation or production process termination;\n",
)

epic = Path("docs/roadmap/epics/EPIC-05-runner-protocol-v2.md")
replace_once(epic, "| Document version | 1.7.0 |", "| Document version | 1.7.1 |")
replace_once(
    epic,
    "validated again on `main`. It uses the durable ledger for restart replay without connecting to\nreal capabilities or the legacy executor. `FINAL` remains false: production execution integration\nis `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and bounded live\ncancellation has not been demonstrated against real execution.\n",
    "validated again on `main`. It uses the durable ledger for restart replay without connecting to\nreal capabilities or the legacy executor. Block 7 is now `IMPLEMENTING`: a repository-local POSIX\nprocess supervisor owns bounded process-group timeout, cancellation and residue cleanup but is\nnot connected to any adapter. `FINAL` remains false: production execution integration is\n`NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and bounded live\ncancellation has not been demonstrated through a Runner Protocol adapter.\n",
)
replace_once(
    epic,
    "## 15. As-built / final architecture\n",
    "### Block 7 — supervised process boundary (`IMPLEMENTING`)\n\n- Branch: `feat/epic-05-supervised-process-boundary`\n- SDK path: `platform/runner-protocol/src/runner_protocol_v2/supervision.py`\n- Documentation: `platform/runner-protocol/supervised-process-boundary.md`\n- Platform: POSIX process groups only\n- Invocation: absolute executable vector, `shell=False`, isolated standard input\n- Lifecycle: new session/process group, bounded output, `SIGTERM` then `SIGKILL`\n- Residue rule: surviving descendants prevent success and are actively cleaned\n- Cleanup failure: explicit `CLEANUP_FAILED`, never eligible for `PASS`\n- Adapter integration: `NOT_RUN`\n- Real capability execution: `NOT_RUN`\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nThe block must prove clean exit, hard timeout, external cancellation, forced termination,\ndescendant cleanup, output truncation and unsafe-specification refusal. It remains an execution\nprimitive rather than authorization, sandboxing, capability mapping or evidence handling.\n\n## 15. As-built / final architecture\n",
)
replace_once(
    epic,
    "| 2026-08-06 | 1.7.0 | Record API durable synthetic restart replay AS_BUILT with production execution NOT_RUN and promotion blocked. |\n",
    "| 2026-08-06 | 1.7.0 | Record API durable synthetic restart replay AS_BUILT with production execution NOT_RUN and promotion blocked. |\n| 2026-08-06 | 1.7.1 | Start supervised POSIX process boundary with adapter integration and real execution NOT_RUN. |\n",
)

catalogue = Path("roadmap/epics/security-validation-platform-v2-concepts.yaml")
replace_once(
    catalogue,
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate and API durable synthetic restart replay. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate and API durable synthetic restart replay. POSIX supervised-process boundary is IMPLEMENTING without adapter integration. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
)

SELF.unlink()
BRANCH_WORKFLOW.unlink()
