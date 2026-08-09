"""Least-privilege invariants for the committed GitHub Actions workflows.

Every workflow must declare an explicit token permission scope so that a
repository default of write access can never be inherited implicitly. Only the
GHCR publication workflows may request `packages: write`, and no workflow may
request `contents: write` or a blanket `write-all`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github/workflows"

PACKAGES_WRITE_ALLOWED = {
    "publish-dvapi-ghcr.yml",
    "publish-dvga-ghcr.yml",
    "publish-nodegoat-ghcr.yml",
    "publish-pygoat-ghcr.yml",
    "publish-vampi-ghcr.yml",
}


def _workflows() -> list[Path]:
    files = sorted(
        path for path in WORKFLOW_DIR.iterdir() if path.suffix in {".yml", ".yaml"}
    )
    assert files, "no workflows discovered"
    return files


def _load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _effective(document: dict[str, Any], job: dict[str, Any]) -> Any:
    job_permissions = (job or {}).get("permissions")
    if job_permissions is not None:
        return job_permissions
    return document.get("permissions")


def test_every_job_has_an_explicit_permission_scope() -> None:
    for path in _workflows():
        document = _load(path)
        for name, job in (document.get("jobs") or {}).items():
            permissions = _effective(document, job)
            assert permissions is not None, (
                f"{path.name}::{name} inherits the default token permissions"
            )


def test_no_workflow_requests_write_all_or_contents_write() -> None:
    for path in _workflows():
        document = _load(path)
        for name, job in (document.get("jobs") or {}).items():
            permissions = _effective(document, job)
            ref = f"{path.name}::{name}"
            assert permissions != "write-all", f"{ref} requests write-all"
            if isinstance(permissions, dict):
                assert permissions.get("contents", "read") == "read", (
                    f"{ref} requests elevated contents permission"
                )


def test_packages_write_is_restricted_to_publication_workflows() -> None:
    for path in _workflows():
        document = _load(path)
        for name, job in (document.get("jobs") or {}).items():
            permissions = _effective(document, job)
            if not isinstance(permissions, dict):
                continue
            if permissions.get("packages") == "write":
                assert path.name in PACKAGES_WRITE_ALLOWED, (
                    f"{path.name}::{name} requests packages: write outside publication scope"
                )


def test_publication_allowlist_has_no_stale_entries() -> None:
    present = {path.name for path in _workflows()}
    stale = sorted(PACKAGES_WRITE_ALLOWED - present)
    assert not stale, f"stale publication workflow allowlist entries: {stale}"
