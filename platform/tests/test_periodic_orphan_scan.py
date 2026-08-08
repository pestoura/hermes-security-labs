from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/lab-lifecycle/periodic_orphan_scan.py"
spec = importlib.util.spec_from_file_location("periodic_orphan_scan", PATH)
assert spec and spec.loader
scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scan
spec.loader.exec_module(scan)


def test_first_scan_is_due_and_interval_is_enforced() -> None:
    assert scan.scan_due(now="2026-08-08T20:00:00Z", last_observed_at=None, interval_seconds=300)
    assert not scan.scan_due(
        now="2026-08-08T20:04:59Z",
        last_observed_at="2026-08-08T20:00:00Z",
        interval_seconds=300,
    )
    assert scan.scan_due(
        now="2026-08-08T20:05:00Z",
        last_observed_at="2026-08-08T20:00:00Z",
        interval_seconds=300,
    )


def test_successful_read_only_scanner_builds_complete_observation() -> None:
    value = scan.build_periodic_observation(
        observation_id="obs-001",
        observed_at="2026-08-08T20:00:00Z",
        lifecycle_records=[],
        scanner=lambda: [
            {
                "resource_ref": "resource-001",
                "kind": "container",
                "lab_id": "lab-001",
                "campaign_id": "campaign-001",
            }
        ],
    )
    assert value["scanner_state"] == "COMPLETE"
    assert len(value["resources"]) == 1


def test_scanner_failure_fails_closed_as_unavailable_without_stale_resources() -> None:
    def broken():
        raise RuntimeError("synthetic scanner unavailable")

    value = scan.build_periodic_observation(
        observation_id="obs-002",
        observed_at="2026-08-08T20:00:00Z",
        lifecycle_records=[],
        scanner=broken,
    )
    assert value["scanner_state"] == "UNAVAILABLE"
    assert value["resources"] == []


def test_module_exposes_no_cleanup_or_mutation_primitive() -> None:
    forbidden = {"delete", "remove", "stop", "kill", "cleanup", "reconcile"}
    assert forbidden.isdisjoint(set(dir(scan)))
