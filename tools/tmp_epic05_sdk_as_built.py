#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 SDK AS_BUILT record."""

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
    replace_once(epic, "| Document version | 1.3.1 |", "| Document version | 1.4.0 |")
    replace_once(
        epic,
        "validated on `main`. `FINAL` remains false because no real runner adapter has yet\n"
        "demonstrated end-to-end conformance, idempotent effects or bounded live cancellation.\n"
        "A repository-local importable SDK is being extracted as block 3 before any real adapter\n"
        "is implemented, preventing adapter-specific copies of canonical validation logic.",
        "validated on `main`. The repository-local SDK was then integrated through pull request\n"
        "[#109](https://github.com/pestoura/hermes-security-labs/pull/109) and validated again on\n"
        "`main`. `FINAL` remains false because no real runner adapter has yet demonstrated\n"
        "end-to-end conformance, idempotent effects or bounded live cancellation.",
    )
    replace_once(
        epic,
        "### Block 3 — repository-local importable SDK (`IMPLEMENTING`)\n\n"
        "- Branch: `refactor/epic-05-runner-protocol-sdk`\n"
        "- Package: `runner_protocol_v2`\n"
        "- Source: `platform/runner-protocol/src/runner_protocol_v2/`\n"
        "- Canonical schemas: retained once under `platform/runner-protocol/schemas/`\n"
        "- CLI: thin wrapper over the SDK\n"
        "- Contract resolution: editable repository root or explicit `RUNNER_PROTOCOL_CONTRACT_ROOT`\n"
        "- Missing contract artefacts: fail closed\n"
        "- Existing API, DevSecOps and AI/MCP adapters: `NOT_RUN`\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "This block is a prerequisite for adapters. It must demonstrate direct package import, canonical\n"
        "contract resolution, rejection of an incomplete explicit contract root and absence of duplicate\n"
        "validation implementations before merge.\n",
        "### Block 3 — repository-local importable SDK (`AS_BUILT`)\n\n"
        "- Branch: `refactor/epic-05-runner-protocol-sdk`\n"
        "- Pull request: [#109](https://github.com/pestoura/hermes-security-labs/pull/109)\n"
        "- Validated head: `8216e733bf87ab89e41fd470e15653ae0c8e1b91`\n"
        "- Squash merge: `dd742e41787bfcaec1feac347abf94c73d5b59fd`\n"
        "- Package: `runner_protocol_v2`\n"
        "- Source: `platform/runner-protocol/src/runner_protocol_v2/`\n"
        "- Canonical schemas: retained once under `platform/runner-protocol/schemas/`\n"
        "- CLI: thin wrapper over the SDK\n"
        "- Contract resolution: editable repository root or explicit `RUNNER_PROTOCOL_CONTRACT_ROOT`\n"
        "- Missing contract artefacts: fail closed\n"
        "- Existing API, DevSecOps and AI/MCP adapters: `NOT_RUN`\n"
        "- Runtime declaration: `NO_RUNTIME_CHANGE`\n\n"
        "The merged implementation demonstrates editable installation, direct import in a clean process,\n"
        "canonical contract resolution, rejection of an incomplete explicit contract root and a guard\n"
        "against reintroducing validation logic into the CLI wrapper.\n",
    )
    replace_once(
        epic,
        "### Delivered contract and conformance architecture\n\n```mermaid\nflowchart LR\n  GW[Execution gateway contract] --> REQ[runner.step.request]\n  REQ --> VAL[Schema and semantic validator]\n  VAL --> IDEM[Fingerprint and idempotency classification]\n  VAL --> RUN[Future runner adapter]",
        "### Delivered contract, SDK and conformance architecture\n\n```mermaid\nflowchart LR\n  SDK[runner_protocol_v2 SDK] --> VAL[Schema and semantic validator]\n  SDK --> IDEM[Fingerprint and idempotency classification]\n  CLI[Thin validate_protocol CLI] --> SDK\n  KIT[Vendor-neutral conformance kit] --> SDK\n  GW[Execution gateway contract] --> REQ[runner.step.request]\n  REQ --> VAL\n  VAL --> RUN[Future runner adapter]",
    )
    replace_once(
        epic,
        "  EV --> OUT\n  KIT[Vendor-neutral conformance kit] --> REF[Test-only reference adapter]",
        "  EV --> OUT\n  KIT --> REF[Test-only reference adapter]",
    )
    replace_once(
        epic,
        "| Secret-leaking adapter | rejected by self-test |",
        "| Secret-leaking adapter | rejected by self-test |\n"
        "| PR #109 validated head | `8216e733bf87ab89e41fd470e15653ae0c8e1b91` |\n"
        "| SDK merge SHA | `dd742e41787bfcaec1feac347abf94c73d5b59fd` |\n"
        "| PR #109 validate workflow | success — run `31079273259` |\n"
        "| PR #109 security/gitleaks workflow | success — run `31079273280` |\n"
        "| Post-merge SDK validate workflow | success — run `31079378064` |\n"
        "| Post-merge SDK security/gitleaks workflow | success — run `31079378148` |\n"
        "| Editable install and direct import | passed |\n"
        "| Incomplete explicit contract root | rejected fail-closed |\n"
        "| Generated package metadata | removed and ignored |",
    )
    replace_once(
        epic,
        "### Epic-level criteria not yet met\n",
        "### Block 3 acceptance assessment\n\n"
        "| Criterion | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| One importable canonical SDK | met | `runner_protocol_v2` public package |\n"
        "| CLI contains no duplicate validation logic | met | source guard in SDK tests |\n"
        "| Editable installation and clean-process import | met | CI install/import gates |\n"
        "| Canonical artefacts remain single-source | met | schemas and compatibility remain outside package copies |\n"
        "| Missing explicit contract root fails closed | met | negative SDK test |\n"
        "| Standard-library `platform` collision avoided | met | explicit package namespace |\n"
        "| Real runner conformance | `NOT_RUN` | API, DevSecOps and AI/MCP unchanged |\n\n"
        "### Epic-level criteria not yet met\n",
    )
    replace_once(
        epic,
        "- The kit validates synthetic effects and adapter behaviour; it does not invoke real\n"
        "  security tools or authorize production execution.",
        "- The kit validates synthetic effects and adapter behaviour; it does not invoke real\n"
        "  security tools or authorize production execution.\n"
        "- The SDK uses an explicit package namespace rather than `platform.*` to avoid collision\n"
        "  with Python's standard-library `platform` module.\n"
        "- The SDK deliberately does not package duplicate schemas; non-editable consumers must\n"
        "  provide the canonical contract root explicitly.",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.3.1 | Start block 3 repository-local SDK extraction before implementing real adapters. |",
        "| 2026-08-06 | 1.3.1 | Start block 3 repository-local SDK extraction before implementing real adapters. |\n"
        "| 2026-08-06 | 1.4.0 | Record repository-local SDK AS_BUILT, merge/CI evidence and fail-closed contract resolution. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        '    current_state: "AS_BUILT for contract and conformance-kit blocks. The protocol, semantic validator, isolated JSON-lines harness and controlled good/bad adapter proofs are integrated; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit and repository-local SDK blocks. Canonical validation and fingerprint logic are importable without duplication; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
    )

    contracts = "docs/architecture/contracts/README.md"
    replace_once(
        contracts,
        "contract and conformance-kit blocks `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
        "contract, conformance-kit and SDK blocks `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
    )

    for temporary in (
        ".github/workflows/epic-05-sdk-as-built-once.yml",
        "tools/tmp_epic05_sdk_as_built.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
