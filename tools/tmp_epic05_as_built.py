#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 contract AS_BUILT record."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    start_at = text.index(start)
    end_at = text.index(end, start_at + len(start))
    file_path.write_text(text[:start_at] + replacement + text[end_at:], encoding="utf-8")


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
    replace_once(epic, "| Document version | 1.1.0 |", "| Document version | 1.2.0 |")
    replace_once(
        epic,
        "**IMPLEMENTING** — the first contract-only vertical slice is active on branch\n"
        "`feat/epic-05-runner-protocol-v2`. It defines and validates the protocol without changing\n"
        "existing runners, gateways, packs, laboratories or live runtime behaviour.",
        "**AS_BUILT** — the contract-only Runner Protocol v2 block was integrated through pull\n"
        "request [#105](https://github.com/pestoura/hermes-security-labs/pull/105) and validated\n"
        "again on `main`. `FINAL` remains false because no runner adapter has yet demonstrated\n"
        "end-to-end conformance, idempotent effects or bounded live cancellation.",
    )
    replace_once(epic, "| AS_BUILT | no |", "| AS_BUILT | yes |")

    section14 = """## 14. Implementation notes

> Reserved lifecycle section. This section records the contract implementation integrated in
> `main`. It does not claim live runner conformance or runtime enforcement.

### Block 1 — typed contract and semantic validation

- Branch: `feat/epic-05-runner-protocol-v2`
- Umbrella issue: [#80](https://github.com/pestoura/hermes-security-labs/issues/80)
- Pull request: [#105](https://github.com/pestoura/hermes-security-labs/pull/105)
- Validated head: `bd8d44bd3bd8b00e8da39665bcb80489486d1276`
- Squash merge: `3f9753ea2e1db5750f971f01bb1dbfea558723fb`
- Runtime declaration: `NO_RUNTIME_CHANGE`
- Canonical location: `platform/runner-protocol/`
- Existing runner, gateway and pack execution code remained unchanged.

### Corrections made before merge

- The initial negative test correctly rejected a request missing `attempt_id`, but the JSON
  Schema `oneOf` diagnostic hid the actionable leaf error. The validator was improved to
  report nested leaf diagnostics without weakening schema enforcement.
- A branch-local workflow could not publish the CI workflow update because its token lacked
  workflow-write permission. Contract changes were published separately and the permanent CI
  gate was applied through the GitHub connector. No permission was broadened.
- Temporary branch-local workflows were removed before the PR diff and merge.

"""
    replace_between(
        epic,
        "## 14. Implementation notes\n",
        "## 15. As-built / final architecture\n",
        section14,
    )

    section15 = """## 15. As-built / final architecture

> Reserved lifecycle section. This is the AS_BUILT record for the contract-only block. The
> umbrella may not be closed until the runner adapters and epic-level acceptance criteria are
> implemented and this section is updated to `FINAL`.

### Delivered contract architecture

```mermaid
flowchart LR
  GW[Execution gateway contract] --> REQ[runner.step.request]
  REQ --> VAL[Schema and semantic validator]
  VAL --> IDEM[Fingerprint and idempotency classification]
  VAL --> RUN[Future runner adapter]
  RUN -. optional progress .-> PROG[runner.progress]
  GW -. cancellation .-> CANCEL[request and acknowledgement]
  RUN --> EV[Sanitized evidence reference]
  RUN --> OUT[runner.outcome]
  EV --> OUT
```

The delivered implementation is a repository-owned protocol contract and validation library.
It does not dispatch work and it has no process, network, container or laboratory side effects.

### Evidence

| Evidence | Result |
| --- | --- |
| PR #105 validated head | `bd8d44bd3bd8b00e8da39665bcb80489486d1276` |
| Merge SHA | `3f9753ea2e1db5750f971f01bb1dbfea558723fb` |
| PR validate workflow | success — run `31076832508` |
| PR security/gitleaks workflow | success — run `31076832409` |
| Post-merge main validate workflow | success — run `31076955536` |
| Post-merge main security/gitleaks workflow | success — run `31076955527` |
| Runner Protocol tests | 17 passed |
| Roadmap/document lifecycle directed tests | 751 passed before PR |
| Runtime validation | `NOT_APPLICABLE` — `NO_RUNTIME_CHANGE` |

### Block 1 acceptance assessment

| Criterion | Result | Evidence |
| --- | --- | --- |
| Four correlation IDs required | met | schema and negative test |
| Terminal evidence reference required | met | schema and `PASS`/empty-evidence tests |
| Same effect has stable fingerprint across attempts | met | semantic validator and replay test |
| Changed effect under same key is conflict | met | `IDEMPOTENCY_CONFLICT` test |
| Timeout/cancellation budgets ordered and bounded | met | semantic validation and negative tests |
| Retries limited to transient taxonomy | met | stable retryability validation |
| Raw secret fields rejected | met | recursive semantic check and test |
| No false runner conformance claim | met | compatibility matrix remains `contract_only` / `NOT_RUN` |

### Epic-level criteria not yet met

| Criterion | State | Required next evidence |
| --- | --- | --- |
| Correlation propagated by every adapter | `NOT_RUN` | API, DevSecOps and AI/MCP adapter conformance |
| Same idempotency key never duplicates effects | `NOT_RUN` | persistent ledger and effect-level replay tests |
| Cancellation observable and bounded live | `NOT_RUN` | supervised process/cancellation integration tests |
| Error taxonomy normalized end to end | `NOT_RUN` | adapter and gateway integration tests |

### Differences from intent

- The contract is a single versioned schema bundle with message variants rather than separate
  top-level schemas. This keeps one protocol version and one compatibility boundary.
- Progress is optional by default. Required progress can be selected per capability later.
- Every terminal outcome requires evidence, including pre-execution refusal and timeout. These
  use decision/protocol evidence and do not falsely claim execution evidence.
- The block introduced deterministic fingerprint classification but deliberately did not
  implement a persistent replay ledger.

### Limitations and residual risk

- No existing runner adapter consumes or emits Runner Protocol v2 messages.
- Schema-valid requests may still be unauthorized; Hermes authorization remains mandatory.
- Cancellation and hard timeout are contract semantics only until supervised runtime support
  is implemented.
- Fingerprint classification does not itself prevent duplicate effects without a persistent,
  atomic idempotency ledger.
- Evidence references are structurally validated but the Evidence Plane and chain-of-custody
  implementation remain later work.
- The umbrella #80 remains `IMPLEMENTING`; this block must not be treated as `FINAL`.

"""
    replace_between(
        epic,
        "## 15. As-built / final architecture\n",
        "## 16. Document change log\n",
        section15,
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.1.0 | Set IMPLEMENTING; define block 1 contract scope, decisions, validation plan and limits. |",
        "| 2026-08-06 | 1.1.0 | Set IMPLEMENTING; define block 1 contract scope, decisions, validation plan and limits. |\n"
        "| 2026-08-06 | 1.2.0 | Record contract block AS_BUILT, merge/CI evidence, acceptance assessment and residual limitations. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        "    status: implementing\n",
        "    status: as_built\n",
    )
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        '    current_state: "IMPLEMENTING. Runner Protocol v2 contract bundle, semantic validator, compatibility matrix and conformance tests are active; no existing runner is yet conformant."\n',
        '    current_state: "AS_BUILT for the contract block. Runner Protocol v2 schema, semantic validator, compatibility matrix and CI conformance tests are integrated; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
    )

    backlog = "roadmap/epics/security-validation-platform-v2.yaml"
    replace_in_section(
        backlog,
        "  - id: SVP2-B-02\n",
        "  - id: SVP2-B-03\n",
        "    status: proposed\n",
        "    status: implementing\n",
    )
    replace_in_section(
        backlog,
        "  - id: SVP2-B-02\n",
        "  - id: SVP2-B-03\n",
        '"status:proposed"',
        '"status:implementing"',
    )

    contracts = "docs/architecture/contracts/README.md"
    replace_once(
        contracts,
        "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | `IMPLEMENTING`; contract in [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout or cancellation is a normalized non-success outcome |",
        "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract block `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout or cancellation is a normalized non-success outcome |",
    )

    for temporary in (
        ".github/workflows/epic-05-as-built-once.yml",
        ".github/workflows/epic-05-as-built-once-v2.yml",
        "tools/tmp_epic05_as_built.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
