"""Hermetic tests for the deterministic host-capacity preflight.

Every case feeds an injected measurement snapshot: no test reads the real
disk, memory, swap or Docker state, so results are identical on any runner.
"""

from __future__ import annotations

import io
import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

DEPLOYMENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DEPLOYMENT_DIR.parent
sys.path.insert(0, str(DEPLOYMENT_DIR))

import capacity_preflight as cp  # noqa: E402

CONFIG_PATH = REPO_ROOT / "config" / "resource-governance.yaml"


def snapshot(**overrides):
    base = {
        "disks": [
            {"label": "root", "path": "/", "total": 1000, "used": 100, "free": 900},
            {"label": "tmp", "path": "/tmp", "total": 1000, "used": 100, "free": 900},
        ],
        "memory": {"total": 1000, "available": 900, "used": 100},
        "swap": {"total": 1000, "used": 100, "free": 900},
        "containers": 1,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def config():
    return cp.DEFAULT_CONFIG


# --- classification -------------------------------------------------------


@pytest.mark.parametrize(
    "used_pct,expected",
    [(0.0, "ok"), (79.9, "ok"), (80.0, "warn"), (89.9, "warn"), (90.0, "critical"), (100.0, "critical")],
)
def test_classify_boundaries_are_inclusive(used_pct, expected):
    assert cp._classify(used_pct, 80.0, 90.0) == expected


def test_classify_none_is_unknown_not_ok():
    """Fail-closed: a missing measurement must never be reported as healthy."""
    assert cp._classify(None, 80.0, 90.0) == "unknown"


# --- positive cases -------------------------------------------------------


def test_all_green_snapshot_is_ok(config):
    report = cp.evaluate(snapshot(), config, "test", now=0.0)
    assert report.overall_status == "ok"
    assert {r.name for r in report.resources} == {"disk", "memory", "swap", "containers"}


def test_self_test_snapshot_is_green(config):
    report = cp.evaluate(cp._SELF_TEST_SNAPSHOT, config, "self-test", now=0.0)
    assert report.overall_status == "ok"


def test_report_is_json_serialisable_and_versioned(config):
    report = cp.evaluate(snapshot(), config, "test", now=0.0)
    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["schema_version"] == cp.REPORT_SCHEMA_VERSION
    assert payload["tool_version"] == cp.TOOL_VERSION
    assert payload["generated_at"] == "1970-01-01T00:00:00+00:00"
    assert payload["source"] == "test"


def test_metrics_are_emitted_per_resource(config):
    report = cp.evaluate(snapshot(), config, "test", now=0.0)
    # one gauge + one state_set per resource
    assert len(report.metrics) == 2 * len(report.resources)
    assert any(m["name"] == "hsl.host.disk.usage_ratio" for m in report.metrics)
    assert all("attributes" in m for m in report.metrics)


# --- negative / threshold cases ------------------------------------------


def test_disk_root_critical_drives_overall(config):
    raw = snapshot(
        disks=[
            {"label": "root", "path": "/", "total": 1000, "used": 950, "free": 50},
            {"label": "tmp", "path": "/tmp", "total": 1000, "used": 100, "free": 900},
        ]
    )
    report = cp.evaluate(raw, config, "test", now=0.0)
    assert report.overall_status == "critical"
    root = next(r for r in report.resources if r.label == "root")
    assert root.status_class == "critical"


def test_tmp_uses_its_own_threshold_key(config):
    raw = snapshot(
        disks=[{"label": "tmp", "path": "/tmp", "total": 1000, "used": 850, "free": 150}]
    )
    report = cp.evaluate(raw, config, "test", now=0.0)
    tmp = next(r for r in report.resources if r.label == "tmp")
    assert tmp.status_class == "warn"
    assert tmp.warn == 80.0 and tmp.critical == 90.0


def test_memory_warn(config):
    report = cp.evaluate(snapshot(memory={"total": 1000, "available": 150, "used": 850}), config, "t", now=0.0)
    mem = next(r for r in report.resources if r.name == "memory")
    assert mem.status_class == "warn"


def test_swap_threshold_is_stricter_than_memory(config):
    """60% swap is a warn even though 60% memory would be ok."""
    raw = snapshot(swap={"total": 1000, "used": 600, "free": 400})
    report = cp.evaluate(raw, config, "test", now=0.0)
    sw = next(r for r in report.resources if r.name == "swap")
    assert sw.status_class == "warn"
    assert sw.warn == 50.0


def test_container_budget_saturation(config):
    report = cp.evaluate(snapshot(containers=24), config, "test", now=0.0)
    c = next(r for r in report.resources if r.name == "containers")
    assert c.used_pct == 100.0
    assert c.status_class == "critical"
    assert c.evidence == {"running": 24, "budget": 24}


def test_container_budget_warn(config):
    report = cp.evaluate(snapshot(containers=20), config, "test", now=0.0)
    c = next(r for r in report.resources if r.name == "containers")
    assert c.status_class == "warn"


# --- fail-closed / unknown handling --------------------------------------


def test_missing_memory_is_unknown_not_ok(config):
    report = cp.evaluate(snapshot(memory=None), config, "test", now=0.0)
    mem = next(r for r in report.resources if r.name == "memory")
    assert mem.status_class == "unknown"
    assert mem.used_pct is None
    assert report.overall_status == "unknown"


def test_missing_docker_is_unknown_not_zero(config):
    report = cp.evaluate(snapshot(containers=None), config, "test", now=0.0)
    c = next(r for r in report.resources if r.name == "containers")
    assert c.status_class == "unknown"
    assert report.overall_status == "unknown"


def test_unreadable_disk_is_unknown(config):
    raw = snapshot(disks=[{"label": "root", "path": "/", "error": "unreadable"}])
    report = cp.evaluate(raw, config, "test", now=0.0)
    root = next(r for r in report.resources if r.label == "root")
    assert root.status_class == "unknown"
    assert root.evidence["error"] == "unreadable"


def test_absent_swap_is_unknown_and_does_not_crash(config):
    report = cp.evaluate(snapshot(swap={"total": 0, "used": 0, "free": 0}), config, "t", now=0.0)
    sw = next(r for r in report.resources if r.name == "swap")
    assert sw.status_class == "unknown"


def test_critical_outranks_unknown(config):
    """Rank order: a real critical must not be masked by an unknown signal."""
    raw = snapshot(
        disks=[{"label": "root", "path": "/", "total": 1000, "used": 999, "free": 1}],
        containers=None,
    )
    report = cp.evaluate(raw, config, "test", now=0.0)
    assert report.overall_status == "unknown"
    assert cp.STATUS_RANK["unknown"] > cp.STATUS_RANK["critical"]


# --- config loading -------------------------------------------------------


def test_load_config_none_returns_defaults():
    assert cp.load_config(None) is cp.DEFAULT_CONFIG


def test_repo_policy_file_loads_and_merges():
    cfg = cp.load_config(CONFIG_PATH)
    th = cfg["capacity"]["thresholds"]
    assert th["disk_root"]["critical_pct"] == 90
    assert th["swap"]["warn_pct"] == 50
    assert cfg["capacity"]["container_budget"]["max"] == 24
    # merged, not replaced: defaults survive for untouched keys
    assert "scan_paths" in cfg["capacity"]


def test_repo_policy_drives_evaluation():
    cfg = cp.load_config(CONFIG_PATH)
    report = cp.evaluate(snapshot(), cfg, "test", now=0.0)
    assert report.overall_status == "ok"


def test_malformed_config_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(cp.CapacityError) as exc:
        cp.load_config(bad)
    assert exc.value.code == cp.EXIT_USAGE


# --- CLI ------------------------------------------------------------------


def test_exit_codes_map_to_status():
    assert cp._exit_for("ok") == cp.EXIT_OK
    assert cp._exit_for("warn") == cp.EXIT_WARN
    assert cp._exit_for("critical") == cp.EXIT_CRITICAL
    assert cp._exit_for("unknown") == cp.EXIT_UNKNOWN


def test_cli_self_test_is_host_independent(tmp_path: Path):
    """--self-test must be GREEN regardless of the runner's real capacity."""
    out = tmp_path / "report.json"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cp.main(["inspect", "--self-test", "--output", str(out)])
    assert code == cp.EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"] == "self-test"
    assert payload["overall_status"] == "ok"


def test_cli_self_test_with_repo_config(tmp_path: Path):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cp.main(["inspect", "--self-test", "--config", str(CONFIG_PATH)])
    assert code == cp.EXIT_OK
    assert json.loads(buf.getvalue())["overall_status"] == "ok"


def test_cli_subprocess_self_test_green():
    res = subprocess.run(
        [sys.executable, str(DEPLOYMENT_DIR / "capacity_preflight.py"), "inspect", "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == cp.EXIT_OK, res.stderr
    assert json.loads(res.stdout)["overall_status"] == "ok"


def test_cli_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cp.main([])
