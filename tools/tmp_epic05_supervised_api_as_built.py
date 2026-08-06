from __future__ import annotations

from pathlib import Path

SELF = Path(__file__)
WORKFLOW = Path(".github/workflows/epic-05-supervised-api-as-built-once.yml")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


epic = Path("docs/roadmap/epics/EPIC-05-runner-protocol-v2.md")
replace_once(epic, "| Document version | 1.8.1 |", "| Document version | 1.9.0 |")
replace_once(
    epic,
    "cleanup. Block 8 is now `IMPLEMENTING`: an API-family fixed-worker synthetic candidate consumes\nthe ledger and supervisor, proving claim-before-spawn, timeout, asynchronous cancellation and\nfail-closed residue handling without real capabilities. `FINAL` remains false: production\nexecution integration is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`,\nand no sandboxed real capability has been demonstrated.\n",
    "cleanup. The API-family fixed-worker synthetic candidate was then integrated through pull\nrequest [#119](https://github.com/pestoura/hermes-security-labs/pull/119) and validated again on\n`main`. It consumes the ledger and supervisor, proving claim-before-spawn, timeout, asynchronous\ncancellation and fail-closed residue handling without real capabilities. `FINAL` remains false:\nproduction execution integration is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain\n`NOT_RUN`, and no sandboxed real capability has been demonstrated.\n",
)
replace_once(
    epic,
    "### Block 8 — API supervised synthetic-process integration (`IMPLEMENTING`)\n\n- Branch: `feat/epic-05-api-supervised-synthetic-adapter`\n- Adapter: `security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`\n",
    "### Block 8 — API supervised synthetic-process integration (`AS_BUILT`)\n\n- Branch: `feat/epic-05-api-supervised-synthetic-adapter`\n- Pull request: [#119](https://github.com/pestoura/hermes-security-labs/pull/119)\n- Validated head: `0c73ae7cb63ac8a5545c8d4ddc55b00d1543fba2`\n- Squash merge: `bc7e301baf977e041ff267a045bbb8ee592c6455`\n- Adapter: `security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`\n",
)
replace_once(
    epic,
    "The block must prove that request input cannot form a command, completed outcomes replay without\na second process, cancellation persists across restart, and cleanup uncertainty cannot become\nsuccess. It remains synthetic process-level evidence only.\n",
    "The merged block proves that request input cannot form a command, completed outcomes replay\nwithout a second process, cancellation persists across restart, and cleanup uncertainty cannot\nbecome success. It remains synthetic process-level evidence only.\n",
)
replace_once(
    epic,
    "optional local enforcement primitives for durable idempotency and POSIX process supervision. No\nthe fixed-worker synthetic API candidate dispatches controlled repository test processes through\nthe supervisor. No production adapter, network, container, laboratory or customer target is used.\n",
    "optional local enforcement primitives for durable idempotency and POSIX process supervision. The\nfixed-worker synthetic API candidate dispatches controlled repository test processes through the\nsupervisor. No production adapter, network, container, laboratory or customer target is used.\n",
)
replace_once(
    epic,
    "| Runner Protocol tests with supervisor | 43 passed |\n| Adapter consumption of supervisor | `NOT_RUN` |\n",
    "| Runner Protocol tests with supervisor | 43 passed |\n| Adapter consumption of supervisor | fixed synthetic API candidate `AS_BUILT`; production `NOT_RUN` |\n| PR #119 validated head | `0c73ae7cb63ac8a5545c8d4ddc55b00d1543fba2` |\n| Supervised API synthetic merge SHA | `bc7e301baf977e041ff267a045bbb8ee592c6455` |\n| PR #119 validate workflow | success — run `31094891644` |\n| PR #119 security/gitleaks workflow | success — run `31094891414` |\n| Post-merge supervised API validate workflow | success — run `31095007408` |\n| Post-merge supervised API security/gitleaks workflow | success — run `31095007428` |\n| Compatibility state | `PASS_SYNTHETIC_PROCESS` |\n| Production API execution integration | `NOT_RUN` |\n| Sandbox status | `NOT_IMPLEMENTED` |\n",
)
replace_once(
    epic,
    "| Runner Protocol adapter integration | `NOT_RUN` | no adapter imports or consumes the supervisor |\n",
    "| Runner Protocol adapter integration | met for fixed synthetic candidate | block 8 imports and consumes the supervisor |\n",
)
replace_once(
    epic,
    "### Epic-level criteria not yet met\n",
    "### Block 8 acceptance assessment\n\n| Criterion | Result | Evidence |\n| --- | --- | --- |\n| Request input cannot form process specification | met | caller-shaped `argv`, `cwd` and environment test plus source guard |\n| Durable claim precedes process creation | met | adapter control flow and no-claim refusal tests |\n| Successful process replays without second spawn | met | restarted candidate with zero effect count |\n| Non-zero exit normalized without raw stderr | met | `EXECUTION_FAILED` and sanitized stream metadata test |\n| Hard timeout maps to terminal timeout | met | stubborn fixed worker and `TIMEOUT_HARD` test |\n| Cancellation is asynchronous and bounded | met for fixed synthetic worker | progress, acknowledgement, forced cleanup and terminal replay |\n| Descendant residue cannot pass | met | `RESIDUE_CLEANED` maps to non-retryable `INCONCLUSIVE` |\n| Internal readiness and PID files removed | met | post-terminal filesystem assertions |\n| Real capability and authorization create no claim | met | negative durable-record tests |\n| Shutdown cleans active tracked processes | met | synthetic shutdown integration test |\n| Raw process output not persisted | met | hashes/lengths only and raw-string absence tests |\n| Sandbox and resource isolation | `NOT_RUN` | process groups do not provide containment |\n| Production API capability execution | `NOT_RUN` | fixed synthetic worker only |\n| Production promotion | blocked | compatibility 1.3 and explicit no-promotion status |\n\n### Epic-level criteria not yet met\n",
)
replace_once(
    epic,
    "| Same idempotency key never duplicates effects | `PARTIAL` | synthetic API restart replay is AS_BUILT; production adapter effect-level integration remains `NOT_RUN` |\n| Cancellation observable and bounded live | `PARTIAL` | local POSIX supervision is AS_BUILT; adapter-level protocol integration remains `NOT_RUN` |\n| Error taxonomy normalized end to end | `NOT_RUN` | adapter and gateway integration tests |\n",
    "| Same idempotency key never duplicates effects | `PARTIAL` | synthetic effect and fixed-process replay are AS_BUILT; production effect integration remains `NOT_RUN` |\n| Cancellation observable and bounded live | `PARTIAL` | fixed synthetic API process is AS_BUILT; production adapter cancellation remains `NOT_RUN` |\n| Error taxonomy normalized end to end | `PARTIAL` | fixed synthetic process states are normalized; gateway and production adapters remain `NOT_RUN` |\n",
)
replace_once(
    epic,
    "- The process supervisor was delivered as a reusable SDK primitive before adapter integration so\n  timeout and cancellation behaviour can be reviewed independently from capability mapping.\n  Production integration still requires a supervised synthetic adapter and later real capability\n  mapping under stronger sandbox and authorization controls.\n",
    "- The process supervisor was delivered as a reusable SDK primitive before adapter integration so\n  timeout and cancellation behaviour could be reviewed independently from capability mapping.\n  Block 8 then connected only a fixed synthetic worker; real capability mapping still requires\n  stronger sandbox, authorization, target and evidence controls.\n",
)
replace_once(
    epic,
    "- Local cancellation, hard timeout and process-group cleanup are implemented in the SDK, but\n  no Runner Protocol adapter currently invokes the supervisor or translates its states into\n  protocol outcomes.\n",
    "- Local cancellation, hard timeout and process-group cleanup are integrated with the fixed\n  synthetic API candidate, but no production Runner Protocol adapter invokes the supervisor or\n  executes a real capability.\n",
)
replace_once(
    epic,
    "| 2026-08-06 | 1.8.1 | Start fixed-worker API supervised synthetic-process integration with production execution blocked. |\n",
    "| 2026-08-06 | 1.8.1 | Start fixed-worker API supervised synthetic-process integration with production execution blocked. |\n| 2026-08-06 | 1.9.0 | Record fixed-worker API supervised synthetic-process integration AS_BUILT with sandbox and production execution NOT_RUN. |\n",
)

candidate_doc = Path("security/packs/api/docs/runner-protocol-supervised-candidate.md")
replace_once(
    candidate_doc,
    "`IMPLEMENTING` — block 8 of `EPIC-05 — Runner Protocol v2`.\n",
    "`AS_BUILT` — block 8 of `EPIC-05 — Runner Protocol v2`, integrated through pull request\n[#119](https://github.com/pestoura/hermes-security-labs/pull/119).\n",
)
replace_once(
    candidate_doc,
    "## Explicit limitations\n",
    "## Integrated evidence\n\n- Validated head: `0c73ae7cb63ac8a5545c8d4ddc55b00d1543fba2`\n- Squash merge: `bc7e301baf977e041ff267a045bbb8ee592c6455`\n- PR validate: `31094891644` — success\n- PR security/gitleaks: `31094891414` — success\n- Post-merge validate: `31095007408` — success\n- Post-merge security/gitleaks: `31095007428` — success\n- Compatibility: `PASS_SYNTHETIC_PROCESS`\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nAll process execution used only the fixed synthetic worker. No real capability, customer target,\nlaboratory, Hermes, Kali MCP or security tool was invoked.\n\n## Explicit limitations\n",
)

protocol_readme = Path("platform/runner-protocol/README.md")
replace_once(
    protocol_readme,
    "and a fixed-worker supervised candidate is `IMPLEMENTING` with `PASS_SYNTHETIC_PROCESS`; real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
    "and a fixed-worker supervised candidate is `AS_BUILT` with `PASS_SYNTHETIC_PROCESS`; real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
)

catalogue = Path("roadmap/epics/security-validation-platform-v2-concepts.yaml")
replace_once(
    catalogue,
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate, API durable synthetic restart replay and POSIX process supervisor. Fixed-worker API supervised synthetic-process integration is IMPLEMENTING with PASS_SYNTHETIC_PROCESS. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate, API durable synthetic restart replay, POSIX process supervisor and fixed-worker API supervised synthetic-process integration. Supervised status is PASS_SYNTHETIC_PROCESS; sandbox and production execution remain NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
)

inventory = Path("docs/architecture/contracts/README.md")
replace_once(
    inventory,
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK, durable ledger and POSIX process supervisor `AS_BUILT`; API in-memory/durable candidates `PASS_SYNTHETIC`; fixed-worker supervised candidate `IMPLEMENTING` / `PASS_SYNTHETIC_PROCESS`; production execution and other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout, cancellation or verified cleanup is a normalized non-success outcome |\n",
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK, durable ledger, POSIX process supervisor and fixed-worker API supervised candidate `AS_BUILT`; API protocol status `PASS_SYNTHETIC` / `PASS_SYNTHETIC_PROCESS`; sandbox, production execution and other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout, cancellation or verified cleanup is a normalized non-success outcome |\n",
)

SELF.unlink()
WORKFLOW.unlink()
