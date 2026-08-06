#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 API candidate AS_BUILT record."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_in_section(path: str, start: str, end: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    start_at = text.index(start)
    end_at = text.index(end, start_at + len(start))
    section = text[start_at:end_at]
    count = section.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: section {start.strip()!r} expected one occurrence, "
            f"found {count}: {old!r}"
        )
    section = section.replace(old, new, 1)
    file_path.write_text(text[:start_at] + section + text[end_at:], encoding="utf-8")


def main() -> None:
    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.4.1 |", "| Document version | 1.5.0 |")
    replace_once(
        epic,
        "`main`. `FINAL` remains false because no real runner adapter has yet demonstrated\n"
        "end-to-end production conformance, durable idempotent effects or bounded live\n"
        "cancellation. An API-family candidate is now being implemented in synthetic-only, opt-in\n"
        "mode; this does not satisfy the remaining epic-level criteria.",
        "`main`. The API-family synthetic-only candidate was subsequently integrated through pull\n"
        "request [#111](https://github.com/pestoura/hermes-security-labs/pull/111) and validated\n"
        "again on `main`. `FINAL` remains false: production execution integration is `NOT_RUN`,\n"
        "promotion is blocked, and no runner family has demonstrated durable idempotent effects\n"
        "or bounded live cancellation against real execution.",
    )
    replace_once(
        epic,
        "### Block 4 — API-family conformance candidate (`IMPLEMENTING`)\n\n"
        "- Branch: `feat/epic-05-api-adapter-candidate`\n"
        "- Adapter path: `security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py`\n"
        "- Activation: explicit `--conformance-only`\n"
        "- Supported scope: synthetic `conformance.*` capabilities only\n"
        "- Authorization: synthetic `authz/conformance/active` only\n"
        "- State: in-memory test ledger only\n"
        "- Vendor-neutral conformance: `PASS_SYNTHETIC`\n"
        "- Execution integration: `NOT_RUN`\n"
        "- Promotion status: blocked\n"
        "- Legacy `execute_runbook` / bridge path: unchanged and disconnected\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "The block must prove conformance, refusal of real capabilities and authorization references,\n"
        "absence of legacy execution imports/calls and absence of persistent/network/process side effects.\n"
        "A green result is not production conformance evidence.\n",
        "### Block 4 — API-family conformance candidate (`AS_BUILT`)\n\n"
        "- Branch: `feat/epic-05-api-adapter-candidate`\n"
        "- Pull request: [#111](https://github.com/pestoura/hermes-security-labs/pull/111)\n"
        "- Validated head: `7227cd52eafef7a7f3042a3a088c24e907447758`\n"
        "- Squash merge: `be74ee87c30620ec811b062d3a85e216d7751b50`\n"
        "- Adapter path: `security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py`\n"
        "- Activation: explicit `--conformance-only`\n"
        "- Supported scope: synthetic `conformance.*` capabilities only\n"
        "- Authorization: synthetic `authz/conformance/active` only\n"
        "- State: in-memory test ledger only\n"
        "- Vendor-neutral conformance: `PASS_SYNTHETIC`\n"
        "- Execution integration: `NOT_RUN`\n"
        "- Promotion status: blocked\n"
        "- Legacy `execute_runbook` / bridge path: unchanged and disconnected\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "The merged candidate passes the vendor-neutral protocol kit, refuses real capabilities and\n"
        "authorization references without effect, and is structurally disconnected from persistence,\n"
        "network, subprocess and legacy execution paths. This remains synthetic conformance only.\n",
    )
    replace_once(
        epic,
        "  VAL --> RUN[Future runner adapter]",
        "  VAL --> API[API synthetic-only candidate]\n  VAL --> RUN[Future production runner adapter]",
    )
    replace_once(
        epic,
        "  RUN -. optional progress .-> PROG[runner.progress]",
        "  API -. synthetic progress .-> PROG[runner.progress]\n  RUN -. optional progress .-> PROG",
    )
    replace_once(
        epic,
        "| Generated package metadata | removed and ignored |",
        "| Generated package metadata | removed and ignored |\n"
        "| PR #111 validated head | `7227cd52eafef7a7f3042a3a088c24e907447758` |\n"
        "| API candidate merge SHA | `be74ee87c30620ec811b062d3a85e216d7751b50` |\n"
        "| PR #111 validate workflow | success — run `31080984814` |\n"
        "| PR #111 security/gitleaks workflow | success — run `31080984997` |\n"
        "| Post-merge API candidate validate workflow | success — run `31081085159` |\n"
        "| Post-merge API candidate security/gitleaks workflow | success — run `31081085183` |\n"
        "| API candidate conformance | `PASS_SYNTHETIC` |\n"
        "| API execution integration | `NOT_RUN` |\n"
        "| API promotion status | blocked |",
    )
    replace_once(
        epic,
        "### Epic-level criteria not yet met\n",
        "### Block 4 acceptance assessment\n\n"
        "| Criterion | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| Explicit conformance-only activation | met | CLI negative/positive tests |\n"
        "| Synthetic protocol conformance | `PASS_SYNTHETIC` | canonical conformance kit in CI |\n"
        "| Real capabilities refused without effect | met | candidate tests and zero effect/ledger checks |\n"
        "| Real authorization reference refused | met | authorization negative test |\n"
        "| Legacy executor and bridge disconnected | met | AST structural guard and unchanged legacy files |\n"
        "| Network/subprocess/file/database effects absent | met | AST guard and candidate implementation |\n"
        "| Production execution integration | `NOT_RUN` | no real capability mapping or execution path |\n"
        "| Production promotion | blocked | compatibility catalogue and no automatic promotion |\n\n"
        "### Epic-level criteria not yet met\n",
    )
    replace_once(
        epic,
        "- No existing runner adapter consumes or emits Runner Protocol v2 messages.",
        "- No production runner adapter consumes or emits Runner Protocol v2 messages; the API\n"
        "  candidate is limited to synthetic conformance and cannot execute real capabilities.",
    )
    replace_once(
        epic,
        "- The SDK deliberately does not package duplicate schemas; non-editable consumers must\n"
        "  provide the canonical contract root explicitly.",
        "- The SDK deliberately does not package duplicate schemas; non-editable consumers must\n"
        "  provide the canonical contract root explicitly.\n"
        "- The first family-specific candidate is deliberately separate from the legacy API executor;\n"
        "  production integration requires a later capability-mapping and supervised execution block.",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.4.1 | Start block 4 API-family candidate in synthetic-only conformance mode with production promotion blocked. |",
        "| 2026-08-06 | 1.4.1 | Start block 4 API-family candidate in synthetic-only conformance mode with production promotion blocked. |\n"
        "| 2026-08-06 | 1.5.0 | Record API synthetic candidate AS_BUILT with PASS_SYNTHETIC evidence, execution NOT_RUN and promotion blocked. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        '    current_state: "AS_BUILT for contract, conformance-kit and SDK blocks; an API-family synthetic-only candidate is IMPLEMENTING with PASS_SYNTHETIC, execution integration NOT_RUN and promotion blocked. DevSecOps and AI/MCP remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK and API synthetic-candidate blocks. The API candidate has PASS_SYNTHETIC with execution integration NOT_RUN and promotion blocked; DevSecOps and AI/MCP remain NOT_RUN."\n',
    )

    inventory = "docs/architecture/contracts/README.md"
    replace_once(
        inventory,
        "API synthetic candidate `IMPLEMENTING` / `PASS_SYNTHETIC`, execution `NOT_RUN`; other adapters `NOT_RUN`",
        "API synthetic candidate `AS_BUILT` / `PASS_SYNTHETIC`, execution `NOT_RUN`; other adapters `NOT_RUN`",
    )

    for temporary in (
        ".github/workflows/epic-05-api-candidate-as-built-once.yml",
        "tools/tmp_epic05_api_candidate_as_built.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
