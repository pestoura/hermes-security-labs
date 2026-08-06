from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


def test_cross_family_supervised_lifecycle_is_fail_closed() -> None:
    compatibility = yaml.safe_load(
        (ROOT / "compatibility.yaml").read_text(encoding="utf-8")
    )
    lifecycle = compatibility["cross_family_supervised_conformance"]

    assert lifecycle == {
        "status": "PASS_SYNTHETIC_PROCESS",
        "scope": "fixed_synthetic_workers_only",
        "harness_path": "platform/runner-protocol/supervised_conformance.py",
        "report_schema": (
            "schemas/supervised-conformance-report.schema.json"
        ),
        "families": ["api", "devsecops", "ai-mcp"],
        "cases": [
            "success",
            "durable-replay",
            "idempotency-conflict",
            "execution-failure",
            "hard-timeout",
            "cancellation",
            "descendant-residue",
            "unsupported-capability-refusal",
            "authorization-refusal",
        ],
        "parity_verdict": "PASS_SYNTHETIC_PROCESS",
        "raw_output_persistence": "none",
        "sandbox_status": "NOT_IMPLEMENTED",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "production_effect_claim": "none",
    }
    assert len(lifecycle["cases"]) == 9
    assert len(lifecycle["cases"]) == len(set(lifecycle["cases"]))

    harness = (REPOSITORY_ROOT / lifecycle["harness_path"]).resolve()
    report_schema = (ROOT / lifecycle["report_schema"]).resolve()
    assert REPOSITORY_ROOT in harness.parents
    assert ROOT in report_schema.parents
    assert harness.is_file()
    assert report_schema.is_file()


def test_cross_family_lifecycle_does_not_promote_runner_families() -> None:
    compatibility = yaml.safe_load(
        (ROOT / "compatibility.yaml").read_text(encoding="utf-8")
    )

    families = compatibility["runner_families"]
    family_ids = [family["id"] for family in families]
    assert family_ids == ["api", "devsecops", "ai-mcp"]
    assert compatibility["cross_family_supervised_conformance"]["families"] == family_ids
    assert {family["execution_integration"] for family in families} == {
        "NOT_RUN"
    }
    assert {family["promotion_status"] for family in families} == {"blocked"}
    assert compatibility["runtime_declaration"] == "NO_RUNTIME_CHANGE"
