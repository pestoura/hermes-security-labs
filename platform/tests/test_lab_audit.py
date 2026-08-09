"""Contract tests for the read-only lab maturity audit."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "platform" / "scripts" / "lab_audit.py"

spec = importlib.util.spec_from_file_location("lab_audit", AUDIT_PATH)
assert spec and spec.loader
lab_audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lab_audit
spec.loader.exec_module(lab_audit)


COMPOSE_CLEAN = """
services:
  app:
    image: example.invalid/app@sha256:{digest}
    healthcheck:
      test: ["CMD", "true"]
    ports:
      - "127.0.0.1:${{APP_HOST_PORT:-9101}}:9101"
    networks: [lab, backend]
  db:
    image: example.invalid/db@sha256:{digest}
    healthcheck:
      test: ["CMD", "true"]
    networks: [backend]
networks:
  lab:
  backend:
    internal: true
""".format(digest="0" * 64)


def _write_env(tmp_path: Path, compose: str, scripts: tuple[str, ...]) -> Path:
    env_dir = tmp_path / "synthetic-lab"
    (env_dir / "scripts").mkdir(parents=True)
    manifest = env_dir / "manifest.yaml"
    manifest.write_text(
        "id: synthetic-lab\nname: Synthetic Lab\nruntime: docker\nstatus: CURRENT\n",
        encoding="utf-8",
    )
    (env_dir / "compose.yaml").write_text(compose, encoding="utf-8")
    for name in scripts:
        (env_dir / "scripts" / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return manifest


ALL_SCRIPTS = (
    "start.sh",
    "stop.sh",
    "reset.sh",
    "destroy.sh",
    "status.sh",
    "smoke.sh",
    "connect-kali.sh",
    "disconnect-kali.sh",
)


def test_complete_environment_passes(tmp_path: Path) -> None:
    manifest = _write_env(tmp_path, COMPOSE_CLEAN, ALL_SCRIPTS)
    result = lab_audit.audit_environment(manifest)
    assert result["verdict"] == lab_audit.VERDICT_PASS
    assert result["population"] == "runtime-managed"
    assert result["fatal"] == []
    assert result["warnings"] == []


def test_missing_lifecycle_script_is_fatal(tmp_path: Path) -> None:
    scripts = tuple(name for name in ALL_SCRIPTS if name != "destroy.sh")
    manifest = _write_env(tmp_path, COMPOSE_CLEAN, scripts)
    result = lab_audit.audit_environment(manifest)
    assert result["verdict"] == lab_audit.VERDICT_FAIL
    assert "missing-script:destroy.sh" in result["fatal"]


def test_non_loopback_publication_is_fatal(tmp_path: Path) -> None:
    compose = COMPOSE_CLEAN.replace('"127.0.0.1:${APP_HOST_PORT:-9101}:9101"', '"9101:9101"')
    manifest = _write_env(tmp_path, compose, ALL_SCRIPTS)
    result = lab_audit.audit_environment(manifest)
    assert result["verdict"] == lab_audit.VERDICT_FAIL
    assert any(finding.startswith("non-loopback-port:") for finding in result["fatal"])


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("unpinned", "unpinned-image:app"),
        ("healthcheck", "missing-healthcheck:app"),
        ("fixed-port", "fixed-host-port:app:127.0.0.1:9101:9101"),
        ("no-internal", "no-internal-network"),
    ],
)
def test_reproducibility_gaps_degrade_without_failing(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    compose = COMPOSE_CLEAN
    if mutation == "unpinned":
        compose = compose.replace("app@sha256:" + "0" * 64, "app:latest")
    elif mutation == "healthcheck":
        compose = compose.replace(
            '    healthcheck:\n      test: ["CMD", "true"]\n    ports:', "    ports:"
        )
    elif mutation == "fixed-port":
        compose = compose.replace("${APP_HOST_PORT:-9101}", "9101")
    elif mutation == "no-internal":
        compose = compose.replace("    internal: true\n", "")
    manifest = _write_env(tmp_path, compose, ALL_SCRIPTS)
    result = lab_audit.audit_environment(manifest)
    assert result["verdict"] == lab_audit.VERDICT_DEGRADED
    assert expected in result["warnings"]
    assert result["fatal"] == []


def test_flat_manifest_is_catalog_only(tmp_path: Path) -> None:
    manifest = tmp_path / "flat-lab.yaml"
    manifest.write_text(
        "id: flat-lab\nname: Flat Lab\nruntime: docker\nstatus: CURRENT\n", encoding="utf-8"
    )
    result = lab_audit.audit_environment(manifest)
    assert result["verdict"] == lab_audit.VERDICT_CATALOG_ONLY
    assert result["population"] == "catalog-only"


def test_repository_catalog_has_no_fatal_findings() -> None:
    failures = [item for item in lab_audit.audit_catalog() if item["verdict"] == "FAIL"]
    assert failures == [], failures


def test_repository_matches_recorded_baseline() -> None:
    completed = subprocess.run(
        [sys.executable, str(AUDIT_PATH), "baseline-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
