#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 conformance-kit AS_BUILT record."""

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
    replace_once(epic, "| Document version | 1.2.1 |", "| Document version | 1.3.0 |")
    replace_once(
        epic,
        "again on `main`. `FINAL` remains false because no runner adapter has yet demonstrated\n"
        "end-to-end conformance, idempotent effects or bounded live cancellation. A vendor-neutral\n"
        "conformance kit is now being implemented as block 2; real runner states remain `NOT_RUN`.",
        "again on `main`. The vendor-neutral conformance kit was subsequently integrated through\n"
        "pull request [#107](https://github.com/pestoura/hermes-security-labs/pull/107) and also\n"
        "validated on `main`. `FINAL` remains false because no real runner adapter has yet\n"
        "demonstrated end-to-end conformance, idempotent effects or bounded live cancellation.",
    )
    replace_once(
        epic,
        "### Block 2 — vendor-neutral conformance kit (`IMPLEMENTING`)\n\n"
        "- Branch: `feat/epic-05-conformance-kit`\n"
        "- Candidate transport: isolated JSON-lines process\n"
        "- Test capabilities: synthetic `conformance.*` only\n"
        "- Report: schema-backed, sanitized and command-hashed\n"
        "- Promotion effect: none; human review mandatory\n"
        "- Real API, DevSecOps and AI/MCP adapters: `NOT_RUN`\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "The block must prove that the kit accepts a deterministic reference adapter and rejects\n"
        "controlled duplicate-effect and secret-leaking adapters before a pull request may be merged.\n",
        "### Block 2 — vendor-neutral conformance kit (`AS_BUILT`)\n\n"
        "- Branch: `feat/epic-05-conformance-kit`\n"
        "- Pull request: [#107](https://github.com/pestoura/hermes-security-labs/pull/107)\n"
        "- Validated head: `61fae45bcc096d8fe71464b5c19dec7146447906`\n"
        "- Squash merge: `944d198a106ebf106631fd18b9c5c5b9aef63942`\n"
        "- Candidate transport: isolated JSON-lines process\n"
        "- Test capabilities: synthetic `conformance.*` only\n"
        "- Report: schema-backed, sanitized and command-hashed\n"
        "- Promotion effect: none; human review mandatory\n"
        "- Real API, DevSecOps and AI/MCP adapters: `NOT_RUN`\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "The merged self-test accepts the deterministic test-only reference adapter and rejects\n"
        "controlled duplicate-effect and secret-leaking adapters. This is evidence about the kit,\n"
        "not production conformance evidence for any real runner family.\n",
    )
    replace_once(
        epic,
        "### Delivered contract architecture\n\n```mermaid\nflowchart LR\n  GW[Execution gateway contract] --> REQ[runner.step.request]\n  REQ --> VAL[Schema and semantic validator]\n  VAL --> IDEM[Fingerprint and idempotency classification]\n  VAL --> RUN[Future runner adapter]\n  RUN -. optional progress .-> PROG[runner.progress]\n  GW -. cancellation .-> CANCEL[request and acknowledgement]\n  RUN --> EV[Sanitized evidence reference]\n  RUN --> OUT[runner.outcome]\n  EV --> OUT\n```",
        "### Delivered contract and conformance architecture\n\n```mermaid\nflowchart LR\n  GW[Execution gateway contract] --> REQ[runner.step.request]\n  REQ --> VAL[Schema and semantic validator]\n  VAL --> IDEM[Fingerprint and idempotency classification]\n  VAL --> RUN[Future runner adapter]\n  RUN -. optional progress .-> PROG[runner.progress]\n  GW -. cancellation .-> CANCEL[request and acknowledgement]\n  RUN --> EV[Sanitized evidence reference]\n  RUN --> OUT[runner.outcome]\n  EV --> OUT\n  KIT[Vendor-neutral conformance kit] --> REF[Test-only reference adapter]\n  KIT --> BAD1[Duplicate-effect adapter]\n  KIT --> BAD2[Secret-leaking adapter]\n  KIT --> REPORT[Sanitized conformance report]\n```",
    )
    replace_once(
        epic,
        "| Runtime validation | `NOT_APPLICABLE` — `NO_RUNTIME_CHANGE` |",
        "| Runtime validation | `NOT_APPLICABLE` — `NO_RUNTIME_CHANGE` |\n"
        "| PR #107 validated head | `61fae45bcc096d8fe71464b5c19dec7146447906` |\n"
        "| Conformance-kit merge SHA | `944d198a106ebf106631fd18b9c5c5b9aef63942` |\n"
        "| PR #107 validate workflow | success — run `31078067384` |\n"
        "| PR #107 security/gitleaks workflow | success — run `31078067277` |\n"
        "| Post-merge conformance validate workflow | success — run `31078149317` |\n"
        "| Post-merge conformance security/gitleaks workflow | success — run `31078149409` |\n"
        "| Reference adapter | accepted by self-test |\n"
        "| Duplicate-effect adapter | rejected by self-test |\n"
        "| Secret-leaking adapter | rejected by self-test |",
    )
    replace_once(
        epic,
        "### Epic-level criteria not yet met\n",
        "### Block 2 acceptance assessment\n\n"
        "| Criterion | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| Language-neutral isolated candidate transport | met | JSON-lines process harness |\n"
        "| Correlation and terminal evidence checked | met | conformance case and protocol validator |\n"
        "| Replay proves no duplicate effect | met for kit/reference adapter | effect-counter case |\n"
        "| Changed effect under same key refused | met for kit/reference adapter | conflict case |\n"
        "| Hard timeout and cooperative cancellation normalized | met for kit/reference adapter | timeout/cancellation cases |\n"
        "| Controlled secret leak detected | met | canary and broken-adapter self-test |\n"
        "| Report sanitized and schema-backed | met | report schema and tests |\n"
        "| Automatic promotion prevented | met | compatibility declaration `promotion_effect: none` |\n"
        "| Real runner conformance | `NOT_RUN` | API, DevSecOps and AI/MCP remain unchanged |\n\n"
        "### Epic-level criteria not yet met\n",
    )
    replace_once(
        epic,
        "- The block introduced deterministic fingerprint classification but deliberately did not\n"
        "  implement a persistent replay ledger.",
        "- The block introduced deterministic fingerprint classification but deliberately did not\n"
        "  implement a persistent replay ledger.\n"
        "- The conformance kit uses a language-neutral JSON-lines control protocol so adapters can\n"
        "  be tested without importing repository-specific Python modules.\n"
        "- The kit validates synthetic effects and adapter behaviour; it does not invoke real\n"
        "  security tools or authorize production execution.",
    )
    replace_once(
        epic,
        "- The umbrella #80 remains `IMPLEMENTING`; this block must not be treated as `FINAL`.",
        "- A conformance-kit `PASS` is necessary but not sufficient for promotion and requires human\n"
        "  review plus adapter-specific integration evidence.\n"
        "- External candidates require an additional sandbox boundary; the harness process boundary\n"
        "  alone is not a complete containment mechanism.\n"
        "- The umbrella #80 remains `IMPLEMENTING`; these blocks must not be treated as `FINAL`.",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.2.1 | Start block 2 vendor-neutral conformance kit while preserving all real adapters as NOT_RUN. |",
        "| 2026-08-06 | 1.2.1 | Start block 2 vendor-neutral conformance kit while preserving all real adapters as NOT_RUN. |\n"
        "| 2026-08-06 | 1.3.0 | Record conformance kit AS_BUILT, merge/CI evidence, controlled rejection proofs and residual limitations. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        '    current_state: "AS_BUILT for the contract block. Runner Protocol v2 schema, semantic validator, compatibility matrix and CI conformance tests are integrated; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract and conformance-kit blocks. The protocol, semantic validator, isolated JSON-lines harness and controlled good/bad adapter proofs are integrated; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
    )

    contracts = "docs/architecture/contracts/README.md"
    replace_once(
        contracts,
        "contract block `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
        "contract and conformance-kit blocks `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
    )

    for temporary in (
        ".github/workflows/epic-05-conformance-as-built-once.yml",
        "tools/tmp_epic05_conformance_as_built.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
