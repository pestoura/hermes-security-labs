"""Fail-closed lifecycle dispatcher tests — no Docker, no runtime changes.

Pure standard library plus PyYAML. Exercises resolution, the readiness gate,
timeouts, destructive-action consent, path confinement and fail-closed behaviour
against fixtures and the real environment manifests. It never starts, stops or
destroys anything: destructive paths are covered by --dry-run and resolution
refusals, and real execution is guarded by subprocess timeouts we never trigger.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "platform" / "scripts"
DISPATCHER = SCRIPTS / "lab_lifecycle.py"

# A directory-based environment that ships a real lifecycle script.
REAL_ENV = "dvapi"
# An environment present only as a flat catalog entry would be UNSUPPORTED; we
# instead assert that a *non-existent* environment is UNSUPPORTED.
UNKNOWN_ENV = "does-not-exist-env"


def _load():
    spec = importlib.util.spec_from_file_location("lab_lifecycle_test", DISPATCHER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lifecycle = _load()


def test_dispatcher_rejects_unknown_action() -> None:
    with pytest.raises(lifecycle.ResolutionError):
        lifecycle.resolve(REAL_ENV, "explode")


def test_dispatcher_refuses_unknown_environment() -> None:
    with pytest.raises(lifecycle.ResolutionError):
        lifecycle.resolve(UNKNOWN_ENV, "start")


def test_dispatcher_resolves_unified_lifecycle_script() -> None:
    res = lifecycle.resolve(REAL_ENV, "start")
    assert res.mode == "unified"
    assert res.script.name == "lifecycle.sh"
    assert res.argv[0] == "bash"
    assert res.script.resolve().relative_to(ROOT.resolve()).as_posix().startswith(
        "platform/environments/"
    )


def test_dispatcher_resolves_discrete_script() -> None:
    # webgoat ships discrete scripts, no unified lifecycle.sh.
    res = lifecycle.resolve("webgoat", "status")
    assert res.mode == "discrete"
    assert res.script.name == "status.sh"


def test_dispatcher_refuses_unsupported_action_for_environment() -> None:
    # juice-shop declares no connect-kali in its manifest lifecycle.
    with pytest.raises(lifecycle.ResolutionError):
        lifecycle.resolve("juice-shop", "connect-kali")


def test_dispatcher_confines_resolved_script_to_env_dir() -> None:
    res = lifecycle.resolve(REAL_ENV, "status")
    assert lifecycle._confined(res.script, res.env_dir)


def test_support_matrix_marks_real_env_supported_and_unknown_unsupported() -> None:
    rows = {row["env_id"]: row for row in lifecycle.support_matrix()}
    assert rows[REAL_ENV]["actions"]["start"] == "SUPPORTED"
    # An environment that does not exist yields no row.
    assert UNKNOWN_ENV not in rows


def test_dry_run_changes_nothing_and_returns_ok() -> None:
    rc = lifecycle.main(["run", REAL_ENV, "start", "--dry-run"])
    assert rc == lifecycle.EXIT_OK


def test_destructive_action_requires_confirmation() -> None:
    rc = lifecycle.main(["run", REAL_ENV, "destroy"])
    assert rc == lifecycle.EXIT_REFUSED


def test_destructive_action_dry_run_is_permitted_without_yes() -> None:
    rc = lifecycle.main(["run", REAL_ENV, "destroy", "--dry-run"])
    assert rc == lifecycle.EXIT_OK


def test_invalid_timeout_is_rejected() -> None:
    with pytest.raises(lifecycle.ResolutionError):
        lifecycle.timeout_for("start", 0)


def test_support_command_json_and_plain() -> None:
    assert lifecycle.main(["support", REAL_ENV, "--json"]) == lifecycle.EXIT_OK
    assert lifecycle.main(["support", REAL_ENV]) == lifecycle.EXIT_OK


def test_support_unknown_env_returns_unsupported() -> None:
    assert lifecycle.main(["support", UNKNOWN_ENV]) == lifecycle.EXIT_UNSUPPORTED


def test_all_actions_are_allowlisted() -> None:
    assert set(lifecycle.ACTIONS) == {
        "start",
        "status",
        "smoke",
        "connect-kali",
        "disconnect-kali",
        "stop",
        "reset",
        "destroy",
    }
    # Safety invariants: no shell, no eval, argument vector only.
    source = DISPATCHER.read_text(encoding="utf-8")
    assert "shell=True" not in source or 'no ``shell=True``' in source
    # The real spawn call must not use a shell.
    assert "subprocess.run(" in source
    assert "shell=True)" not in source
