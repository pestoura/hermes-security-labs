"""Controlled filesystem reset evidence for SVP2-I-01.

This exercises deterministic reset semantics in a disposable temporary laboratory
fixture. It is not evidence of a deployed Docker/Kubernetes/VM lab runtime.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("lab_reset_attestation_ci", HERE / "reset_attestation.py")
assert SPEC and SPEC.loader
ATTEST = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ATTEST
SPEC.loader.exec_module(ATTEST)

FIXTURES = {
    "config.json": b'{"mode":"vulnerable","version":1}\n',
    "seed.txt": b"controlled-fixture\n",
}


def _reset(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for name, data in FIXTURES.items():
        (root / name).write_bytes(data)


def _snapshot(root: Path) -> dict[str, Any]:
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }
    return {"lifecycle": "READY", "fixture_files": files, "file_count": len(files)}


def run_controlled_reset_evidence() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="hex0r-lab-reset-parent-") as parent:
        root = Path(parent) / "lab"
        _reset(root)
        first = _snapshot(root)
        (root / "runtime-drift.txt").write_text("must disappear", encoding="utf-8")
        (root / "seed.txt").write_text("mutated", encoding="utf-8")
        _reset(root)
        second = _snapshot(root)
        result = ATTEST.attest_reset_determinism([first, second])
    return {
        "schema_version": "1.0.0",
        "boundary": "CONTROLLED_CI_FILESYSTEM",
        "deterministic": result.deterministic,
        "canonical_sha256": result.canonical_sha256,
        "execution_count": result.execution_count,
        "codes": list(result.codes),
        "production_lab_runtime": "NOT_RUN",
    }
