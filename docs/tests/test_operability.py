"""Operability guards for the documented operator path.

Pure standard library. No network, no Docker, no runtime changes.

These tests exist because the fastest way to lose an operator is to document a
command that does not do what the document claims. They assert the *documented*
lifecycle surface matches the *shipped* scripts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QUICKSTART = ROOT / "docs" / "quickstart.md"
SCRIPTS = ROOT / "platform" / "scripts"

# Canonical lifecycle wrappers: delegate to the fail-closed dispatcher instead of
# provisioning by themselves. They must never claim a dry run they do not perform.
CANONICAL_WRAPPERS = (
    "lab-start.sh",
    "lab-stop.sh",
    "lab-reset.sh",
    "lab-destroy.sh",
    "lab-smoke.sh",
    "lab-connect-kali.sh",
    "lab-disconnect-kali.sh",
)

# Read-only catalog wrappers that must keep delegating to labctl.py.
READ_ONLY_WRAPPERS = ("lab-list.sh", "lab-status.sh", "lab-validate.sh", "lab-plan.sh")

# Actions every unified lifecycle.sh must dispatch.
REQUIRED_LIFECYCLE_ACTIONS = (
    "start",
    "status",
    "smoke",
    "connect-kali",
    "disconnect-kali",
    "stop",
    "reset",
    "destroy",
)


def _lifecycle_scripts() -> list[Path]:
    return sorted((ROOT / "platform" / "environments").glob("*/*/scripts/lifecycle.sh"))


def test_quickstart_exists_and_is_linked_from_the_documentation_index() -> None:
    assert QUICKSTART.is_file()
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "quickstart.md" in index


def test_quickstart_covers_the_canonical_path() -> None:
    text = QUICKSTART.read_text(encoding="utf-8").lower()
    for stage in ("clone", "validate", "start lab", "connect kali", "evidence", "destroy"):
        assert stage in text, f"quickstart does not cover the {stage!r} stage"


@pytest.mark.parametrize("name", CANONICAL_WRAPPERS)
def test_canonical_wrappers_delegate_to_dispatcher(name: str) -> None:
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    # Canonical wrappers are fail-closed: they delegate to the dispatcher and never
    # claim a dry run they do not perform.
    assert "lab_lifecycle.py" in text, f"{name} must delegate to the dispatcher"
    assert "set -euo pipefail" in text, f"{name} must fail closed on shell errors"
    assert "DRY-RUN" not in text, f"{name} must not claim a dry run it does not perform"
    assert "NOT_IMPLEMENTED" not in text, f"{name} must no longer be a stub"


@pytest.mark.parametrize("name", READ_ONLY_WRAPPERS)
def test_read_only_wrappers_delegate_to_labctl(name: str) -> None:
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "labctl.py" in text, f"{name} must delegate to labctl.py"


def test_dispatcher_is_present_and_readiness_gate_exists() -> None:
    dispatcher = SCRIPTS / "lab_lifecycle.py"
    assert dispatcher.is_file(), "fail-closed lifecycle dispatcher must exist"
    text = dispatcher.read_text(encoding="utf-8")
    assert "fail-closed" in text.lower()
    # The actual spawn must not shell out or eval; ignore the docstring's prose.
    assert "subprocess.run(" in text
    assert "shell=True)" not in text
    assert " eval(" not in text


def test_quickstart_documents_every_canonical_wrapper() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    for name in CANONICAL_WRAPPERS:
        assert name in text, f"quickstart must mention {name}"


@pytest.mark.parametrize(
    "script", _lifecycle_scripts(), ids=lambda p: p.parts[-3]
)
def test_unified_lifecycle_scripts_dispatch_the_documented_actions(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    # Some lifecycle scripts keep the whole `case` on a single line, so anchor on
    # the dispatch token itself rather than on the start of a line.
    missing = [
        action
        for action in REQUIRED_LIFECYCLE_ACTIONS
        if not re.search(rf"(?:^|[\s|]){re.escape(action)}\)", text)
    ]
    assert not missing, f"{script.relative_to(ROOT)} does not dispatch: {missing}"


def test_quickstart_lists_every_environment_that_ships_a_unified_lifecycle() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    missing = [s.parts[-3] for s in _lifecycle_scripts() if s.parts[-3] not in text]
    assert not missing, f"quickstart lifecycle matrix omits: {missing}"
