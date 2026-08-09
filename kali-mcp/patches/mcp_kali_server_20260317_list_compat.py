#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess

EXPECTED_PACKAGE = "mcp-kali-server"
EXPECTED_VERSION = "0.0~git20260317.00154c0-0kali1"
SERVER = Path("/usr/share/mcp-kali-server/server.py")


def package_version() -> str:
    return subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", EXPECTED_PACKAGE],
        text=True,
    ).strip()


def main() -> None:
    version = package_version()
    if version != EXPECTED_VERSION:
        raise SystemExit(
            f"refusing compatibility patch: {EXPECTED_PACKAGE} version {version!r} "
            f"!= expected {EXPECTED_VERSION!r}"
        )

    source = SERVER.read_text(encoding="utf-8")
    if "CommandExecutor expects a string" not in source:
        raise SystemExit("refusing compatibility patch: expected upstream defect marker is absent")

    needle = "    executor = CommandExecutor(command)\n    return executor.execute()"
    if source.count(needle) != 1:
        raise SystemExit("refusing compatibility patch: execute_command insertion point is not unique")

    replacement = (
        "    # Compatibility for Kali mcp-kali-server 20260317: typed endpoints build\n"
        "    # argv lists while this release's CommandExecutor accepts only a shell string.\n"
        "    # shlex.join preserves argv boundaries and quotes shell metacharacters rather\n"
        "    # than concatenating untrusted tool arguments. Generic string commands retain\n"
        "    # their upstream behaviour. Remove this patch when the packaged defect is fixed.\n"
        "    if isinstance(command, (list, tuple)):\n"
        "        command = shlex.join([str(argument) for argument in command])\n"
        "    executor = CommandExecutor(command)\n"
        "    return executor.execute()"
    )
    patched = source.replace(needle, replacement, 1)
    compile(patched, str(SERVER), "exec")
    SERVER.write_text(patched, encoding="utf-8")

    verified = SERVER.read_text(encoding="utf-8")
    if replacement not in verified:
        raise SystemExit("compatibility patch verification failed")

    print(f"patched {EXPECTED_PACKAGE} {version} command-list compatibility")


if __name__ == "__main__":
    main()
