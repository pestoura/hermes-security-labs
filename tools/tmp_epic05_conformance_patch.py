#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 conformance-kit block."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"{path}: marker expected once, found {count}: {marker!r}")
    file_path.write_text(text.replace(marker, content + marker, 1), encoding="utf-8")


def main() -> None:
    conformance = "platform/runner-protocol/conformance.py"
    replace_once(conformance, "import uuid\n", "")

    validator = "platform/runner-protocol/validate_protocol.py"
    insert_before(
        validator,
        "    families = data[\"runner_families\"]\n",
        """    kit = data.get("conformance_kit")
    expected_kit = {
        "status": "available",
        "transport": "json_lines",
        "execution_model": "isolated_candidate_process",
        "reference_adapter": "test_only",
        "report_schema": "schemas/conformance-report.schema.json",
        "promotion_effect": "none",
        "required_verdict_for_promotion": "PASS",
    }
    if kit != expected_kit:
        raise ProtocolValidationError("conformance kit declaration is inconsistent")

    report_schema_path = ROOT / str(kit["report_schema"])
    if not report_schema_path.is_file():
        raise ProtocolValidationError("conformance report schema is missing")
    report_schema = json.loads(report_schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(report_schema)

    migration_gates = data.get("migration_gates")
    required_gates = {
        "schema_validation",
        "semantic_validation",
        "correlation_propagation",
        "idempotency_replay_test",
        "cancellation_timeout_test",
        "evidence_reference_test",
        "secret_redaction_test",
        "conformance_report_pass",
        "human_review_before_promotion",
    }
    if not isinstance(migration_gates, list) or len(migration_gates) != len(
        set(migration_gates)
    ):
        raise ProtocolValidationError("migration gates must be a unique list")
    if set(migration_gates) != required_gates:
        raise ProtocolValidationError("migration gate inventory is incomplete or unexpected")

""",
    )

    readme = "platform/runner-protocol/README.md"
    replace_once(
        readme,
        "- Current implementation state: contract-only; no existing API, DevSecOps or AI/MCP runner is claimed conformant.",
        "- Current implementation state: contract and vendor-neutral conformance kit available; no existing API, DevSecOps or AI/MCP runner is claimed conformant.",
    )
    insert_before(
        readme,
        "## Compatibility\n",
        """## Conformance kit

The vendor-neutral conformance kit is implemented in [`conformance.py`](conformance.py). It
starts a candidate adapter as a disposable process and exchanges language-neutral JSON-lines
control messages over standard input and output.

The candidate must support the test-only control actions `reset`, `dispatch`, `cancel`, `stats`
and `shutdown`. The kit exercises only synthetic `conformance.*` capabilities; it does not
invoke real security tools, customer targets or operational credentials.

The mandatory cases demonstrate:

- propagation of all four correlation identifiers and terminal evidence;
- replay of the same logical effect without increasing the candidate's effect counter;
- refusal of a changed effect under the same idempotency key;
- normalized hard timeout and transient dependency errors;
- cooperative cancellation with acknowledgement and terminal outcome;
- rejection of a controlled secret canary leak.

Results are written as a sanitized report conforming to
[`schemas/conformance-report.schema.json`](schemas/conformance-report.schema.json). The raw
candidate command is not persisted; only its SHA-256 digest is recorded.

A `PASS` verdict is necessary but not sufficient for promotion. It has no automatic promotion
effect, and human review remains mandatory. Third-party or untrusted candidates must run in an
isolated sandbox without customer network access, customer data, real credentials or production
secrets.

The adapter in [`fixtures/reference_adapter.py`](fixtures/reference_adapter.py) is test-only. It
proves the kit can accept a deterministic reference implementation and reject controlled broken
implementations. It is not an API, DevSecOps or AI/MCP runner and provides no production
conformance evidence.

""",
    )
    replace_once(
        readme,
        "- [`compatibility.yaml`](compatibility.yaml)\n- [`tests/test_runner_protocol.py`](tests/test_runner_protocol.py)",
        "- [`compatibility.yaml`](compatibility.yaml)\n- [`conformance.py`](conformance.py)\n- [`schemas/conformance-report.schema.json`](schemas/conformance-report.schema.json)\n- [`fixtures/reference_adapter.py`](fixtures/reference_adapter.py) — test-only\n- [`tests/test_runner_protocol.py`](tests/test_runner_protocol.py)\n- [`tests/test_conformance.py`](tests/test_conformance.py)",
    )

    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.2.0 |", "| Document version | 1.2.1 |")
    replace_once(
        epic,
        "end-to-end conformance, idempotent effects or bounded live cancellation.",
        "end-to-end conformance, idempotent effects or bounded live cancellation. A vendor-neutral\nconformance kit is now being implemented as block 2; real runner states remain `NOT_RUN`.",
    )
    insert_before(
        epic,
        "## 15. As-built / final architecture\n",
        """### Block 2 — vendor-neutral conformance kit (`IMPLEMENTING`)

- Branch: `feat/epic-05-conformance-kit`
- Candidate transport: isolated JSON-lines process
- Test capabilities: synthetic `conformance.*` only
- Report: schema-backed, sanitized and command-hashed
- Promotion effect: none; human review mandatory
- Real API, DevSecOps and AI/MCP adapters: `NOT_RUN`
- Runtime declaration: `NO_RUNTIME_CHANGE`

The block must prove that the kit accepts a deterministic reference adapter and rejects
controlled duplicate-effect and secret-leaking adapters before a pull request may be merged.

""",
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.2.0 | Record contract block AS_BUILT, merge/CI evidence, acceptance assessment and residual limitations. |",
        "| 2026-08-06 | 1.2.0 | Record contract block AS_BUILT, merge/CI evidence, acceptance assessment and residual limitations. |\n| 2026-08-06 | 1.2.1 | Start block 2 vendor-neutral conformance kit while preserving all real adapters as NOT_RUN. |",
    )

    for temporary in (
        ".github/workflows/epic-05-conformance-patch-once.yml",
        "tools/tmp_epic05_conformance_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
