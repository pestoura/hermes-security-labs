"""Hygiene invariants for the Kali MCP lifecycle scripts.

`env.sh` was previously sourced *above* the shebang line. Bash still executed
the files (the kernel falls back to `/bin/sh` for a script without a valid
interpreter line only when invoked directly), but the shebang was inert, the
`set -euo pipefail` guard ran after an unguarded source, and `$0` broke under
`source`/`bash -c` invocation. These tests pin the corrected ordering.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "kali-mcp/scripts"

ENTRYPOINTS = (
    "backup-results.sh",
    "destroy-lab.sh",
    "healthcheck.sh",
    "maintenance.sh",
)


def test_lifecycle_scripts_start_with_a_shebang_and_strict_mode() -> None:
    for name in ENTRYPOINTS:
        lines = (SCRIPT_DIR / name).read_text(encoding="utf-8").splitlines()
        assert lines[0] == "#!/usr/bin/env bash", f"{name} does not start with a shebang"
        assert lines[1] == "set -euo pipefail", f"{name} does not enable strict mode first"


def test_env_is_sourced_after_strict_mode_and_resolved_from_bash_source() -> None:
    for name in ENTRYPOINTS:
        text = (SCRIPT_DIR / name).read_text(encoding="utf-8")
        expected = 'source "$(dirname "${BASH_SOURCE[0]}")/env.sh"'
        assert expected in text, f"{name} does not source env.sh via BASH_SOURCE"
        assert 'source "$(dirname "$0")/env.sh"' not in text, (
            f"{name} still resolves env.sh from $0"
        )
        assert text.index("set -euo pipefail") < text.index(expected), (
            f"{name} sources env.sh before enabling strict mode"
        )


def test_every_shell_file_in_the_repository_has_a_shebang_first() -> None:
    excluded = {".git", ".runtime", "node_modules"}
    offenders = []
    for path in ROOT.rglob("*.sh"):
        if excluded.intersection(path.relative_to(ROOT).parts):
            continue
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        if path.name == "env.sh":
            # env.sh is a sourced fragment, never executed directly.
            continue
        if not first or not first[0].startswith("#!"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"shell entrypoints without a leading shebang: {sorted(offenders)}"
