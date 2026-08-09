#!/usr/bin/env python3
"""Deterministic host-capacity preflight and status model for HSL.

Read-only status probe. This tool never deletes, prunes or mutates host
state. It measures disk, /tmp, memory/swap pressure, container count and
concurrency budgets, classifies each against bounded thresholds, and emits a
low-cardinality, metrics-ready report.

The measurement source is injectable so the classification logic is fully
deterministic under test. The live host source is best-effort: any signal it
cannot read is reported as ``unknown`` rather than failing the preflight.

Metric names follow the USE convention (utilization / saturation / errors)
already present in platform/assurance/observability-maturity-policy.yaml so the
output can be wired into existing observability without duplication. The
``disk_full`` and ``concurrency`` failure cases from that policy are covered by
the disk/tmp and container/concurrency signals here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

TOOL_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3
EXIT_USAGE = 4

STATUS_ORDER = ("ok", "warn", "critical", "unknown")
STATUS_RANK = {s: i for i, s in enumerate(STATUS_ORDER)}

DEFAULT_CONFIG: dict[str, Any] = {
    "capacity": {
        "thresholds": {
            "disk_root": {"warn_pct": 80.0, "critical_pct": 90.0},
            "tmp": {"warn_pct": 80.0, "critical_pct": 90.0},
            "memory": {"warn_pct": 80.0, "critical_pct": 90.0},
            "swap": {"warn_pct": 50.0, "critical_pct": 85.0},
        },
        "container_budget": {"max": 24, "warn_pct": 80.0},
        "scan_paths": [
            {"path": "/", "label": "root"},
            {"path": "/tmp", "label": "tmp"},
            {"path": "~/hermes-security-labs", "label": "repo_home"},
        ],
    }
}

# Deterministic GREEN snapshot used by --self-test so CI never depends on the
# runner's real disk/memory state.
_SELF_TEST_SNAPSHOT: dict[str, Any] = {
    "disks": [
        {"label": "root", "path": "/", "total": 1_000_000, "used": 400_000, "free": 600_000},
        {"label": "tmp", "path": "/tmp", "total": 1_000_000, "used": 400_000, "free": 600_000},
        {"label": "repo_home", "path": "~/hermes-security-labs", "total": 1_000_000, "used": 300_000, "free": 700_000},
    ],
    "memory": {"total": 16_000 * 1024 * 1024, "available": 9_600 * 1024 * 1024, "used": 6_400 * 1024 * 1024},
    "swap": {"total": 8_000 * 1024 * 1024, "used": 400 * 1024 * 1024, "free": 7_600 * 1024 * 1024},
    "containers": 2,
}


class CapacityError(ValueError):
    """Recoverable capacity preflight error with a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_UNKNOWN) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResourceStatus:
    name: str
    label: str
    kind: str
    value: float
    unit: str
    used_pct: float | None
    status_class: str
    warn: float | None
    critical: float | None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightReport:
    overall_status: str
    generated_at: str
    source: str
    schema_version: str
    tool_version: str
    resources: list[ResourceStatus]
    metrics: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "overall_status": self.overall_status,
            "generated_at": self.generated_at,
            "source": self.source,
            "resources": [r.as_dict() for r in self.resources],
            "metrics": self.metrics,
        }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _classify(used_pct: float | None, warn: float | None, critical: float | None) -> str:
    if used_pct is None:
        return "unknown"
    if critical is not None and used_pct >= critical:
        return "critical"
    if warn is not None and used_pct >= warn:
        return "warn"
    return "ok"


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(path: Path | None) -> dict[str, Any]:
    """Load YAML config, merged over built-in defaults. None => defaults only."""
    if path is None:
        return DEFAULT_CONFIG
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - yaml is present in CI
        raise CapacityError("PyYAML is required to read the config file", EXIT_USAGE) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CapacityError("config root must be a mapping", EXIT_USAGE)
    return _deep_merge(DEFAULT_CONFIG, data)


def _parse_meminfo() -> dict[str, float] | None:
    p = Path("/proc/meminfo")
    if not p.exists():
        return None
    data: dict[str, float] = {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        parts = val.strip().split()
        if len(parts) >= 1 and parts[0].isdigit():
            # meminfo values are in kB; convert to bytes.
            data[key.strip()] = float(parts[0]) * 1024
    return data or None


def _read_meminfo_memory() -> dict[str, float] | None:
    info = _parse_meminfo()
    if info is None:
        return None
    total = info.get("MemTotal")
    avail = info.get("MemAvailable")
    if total is None or avail is None:
        return None
    return {"total": total, "available": avail, "used": total - avail}


def _read_meminfo_swap() -> dict[str, float] | None:
    info = _parse_meminfo()
    if info is None:
        return None
    total = info.get("SwapTotal")
    if total is None:
        return None
    if total == 0:
        return {"total": 0.0, "used": 0.0, "free": 0.0}
    free = info.get("SwapFree", 0.0)
    return {"total": total, "used": total - free, "free": free}


def _read_container_count() -> int | None:
    try:
        res = subprocess.run(
            ["docker", "ps", "-q"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return len([line for line in res.stdout.splitlines() if line.strip()])


def live_source(scan_paths: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort live host measurement. Unreadable signals become None."""
    out: dict[str, Any] = {"disks": [], "memory": None, "swap": None, "containers": None}
    for spec in scan_paths:
        raw = os.path.expanduser(spec["path"])
        try:
            usage = shutil.disk_usage(raw)
        except OSError:
            out["disks"].append({"label": spec.get("label", raw), "path": raw, "error": "unreadable"})
            continue
        out["disks"].append(
            {"label": spec.get("label", raw), "path": raw, "total": usage.total, "used": usage.used, "free": usage.free}
        )
    out["memory"] = _read_meminfo_memory()
    out["swap"] = _read_meminfo_swap()
    out["containers"] = _read_container_count()
    return out


def evaluate(raw: dict[str, Any], config: dict[str, Any], source: str, now: float | None = None) -> PreflightReport:
    caps = config["capacity"]
    th = caps["thresholds"]
    resources: list[ResourceStatus] = []

    for d in raw.get("disks", []):
        if "error" in d:
            resources.append(
                ResourceStatus(
                    name="disk", label=d["label"], kind="disk", value=0.0, unit="bytes",
                    used_pct=None, status_class="unknown", warn=None, critical=None,
                    evidence={"path": d["path"], "error": d["error"]},
                )
            )
            continue
        total = float(d["total"])
        used = float(d["used"])
        used_pct = (used / total * 100.0) if total > 0 else None
        key = "tmp" if d["label"] == "tmp" else "disk_root"
        t = th.get(key, th["disk_root"])
        resources.append(
            ResourceStatus(
                name="disk", label=d["label"], kind="disk", value=used_pct or 0.0, unit="percent",
                used_pct=used_pct, status_class=_classify(used_pct, t.get("warn_pct"), t.get("critical_pct")),
                warn=t.get("warn_pct"), critical=t.get("critical_pct"),
                evidence={"path": d["path"], "total_bytes": int(total), "used_bytes": int(used), "free_bytes": int(d["free"])},
            )
        )

    mem = raw.get("memory")
    if mem and mem.get("total"):
        total = float(mem["total"])
        used = float(mem["used"])
        used_pct = (used / total * 100.0) if total > 0 else None
        t = th["memory"]
        resources.append(
            ResourceStatus(
                name="memory", label="memory", kind="memory_pressure", value=used_pct or 0.0, unit="percent",
                used_pct=used_pct, status_class=_classify(used_pct, t.get("warn_pct"), t.get("critical_pct")),
                warn=t.get("warn_pct"), critical=t.get("critical_pct"),
                evidence={"total_bytes": int(total), "used_bytes": int(used), "available_bytes": int(mem.get("available", 0))},
            )
        )
    else:
        resources.append(
            ResourceStatus(
                name="memory", label="memory", kind="memory_pressure", value=0.0, unit="percent",
                used_pct=None, status_class="unknown", warn=None, critical=None,
                evidence={"reason": "meminfo unavailable"},
            )
        )

    sw = raw.get("swap")
    if sw and sw.get("total"):
        total = float(sw["total"])
        used = float(sw["used"])
        used_pct = (used / total * 100.0) if total > 0 else None
        t = th["swap"]
        resources.append(
            ResourceStatus(
                name="swap", label="swap", kind="swap_pressure", value=used_pct or 0.0, unit="percent",
                used_pct=used_pct, status_class=_classify(used_pct, t.get("warn_pct"), t.get("critical_pct")),
                warn=t.get("warn_pct"), critical=t.get("critical_pct"),
                evidence={"total_bytes": int(total), "used_bytes": int(used)},
            )
        )
    else:
        resources.append(
            ResourceStatus(
                name="swap", label="swap", kind="swap_pressure", value=0.0, unit="percent",
                used_pct=None, status_class="unknown", warn=None, critical=None,
                evidence={"reason": "no swap / unavailable"},
            )
        )

    cb = caps["container_budget"]
    c = raw.get("containers")
    if c is not None:
        cnt = int(c)
        maxc = int(cb["max"])
        used_pct = (cnt / maxc * 100.0) if maxc > 0 else None
        resources.append(
            ResourceStatus(
                name="containers", label="containers", kind="container_count", value=float(cnt), unit="count",
                used_pct=used_pct, status_class=_classify(used_pct, cb.get("warn_pct"), 100.0),
                warn=cb.get("warn_pct"), critical=100.0,
                evidence={"running": cnt, "budget": maxc},
            )
        )
    else:
        resources.append(
            ResourceStatus(
                name="containers", label="containers", kind="container_count", value=0.0, unit="count",
                used_pct=None, status_class="unknown", warn=None, critical=None,
                evidence={"reason": "docker unavailable"},
            )
        )

    overall = "ok"
    for r in resources:
        if STATUS_RANK[r.status_class] > STATUS_RANK[overall]:
            overall = r.status_class

    return PreflightReport(
        overall_status=overall,
        generated_at=_iso(now if now is not None else time.time()),
        source=source,
        schema_version=REPORT_SCHEMA_VERSION,
        tool_version=TOOL_VERSION,
        resources=resources,
        metrics=_build_metrics(resources),
    )


def _build_metrics(resources: list[ResourceStatus]) -> list[dict[str, Any]]:
    name_map = {
        "disk": "hsl.host.disk.usage_ratio",
        "memory": "hsl.host.memory.usage_ratio",
        "swap": "hsl.host.swap.usage_ratio",
        "containers": "hsl.host.container.saturation_ratio",
    }
    out: list[dict[str, Any]] = []
    for r in resources:
        value = r.used_pct if r.used_pct is not None else r.value
        out.append(
            {
                "name": name_map.get(r.name, f"hsl.host.{r.name}.usage_ratio"),
                "type": "gauge",
                "unit": "percent",
                "value": round(value, 4),
                "attributes": {"resource": r.label, "class": r.status_class},
            }
        )
        out.append(
            {
                "name": "hsl.host.resource.status",
                "type": "state_set",
                "unit": "status",
                "value": r.status_class,
                "attributes": {"resource": r.label, "kind": r.kind},
            }
        )
    return out


def _exit_for(status: str) -> int:
    return {"ok": EXIT_OK, "warn": EXIT_WARN, "critical": EXIT_CRITICAL, "unknown": EXIT_UNKNOWN}[status]


def cmd_inspect(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config) if args.config else None)
    if args.self_test:
        raw = _SELF_TEST_SNAPSHOT
        source = "self-test"
    else:
        raw = live_source(config["capacity"]["scan_paths"])
        source = "live-host"
    report = evaluate(raw, config, source)
    payload = json.dumps(report.as_dict(), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return _exit_for(report.overall_status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    insp = sub.add_parser("inspect", help="measure host capacity and emit a status report")
    insp.add_argument("--config", default=None)
    insp.add_argument("--output", default=None)
    insp.add_argument("--self-test", action="store_true", help="use a deterministic GREEN snapshot")
    insp.set_defaults(func=cmd_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CapacityError as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}, indent=2), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
