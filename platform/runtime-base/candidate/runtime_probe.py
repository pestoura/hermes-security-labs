import json
import os
import socket
from pathlib import Path


def _write_probe(path: Path) -> bool:
    try:
        path.write_text("probe\n", encoding="utf-8")
        path.unlink()
        return True
    except OSError:
        return False


def _status_field(name: str) -> str | None:
    prefix = f"{name}:"
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _raw_socket_available() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except (PermissionError, OSError):
        return False
    else:
        sock.close()
        return True


def _tcp_socket_available() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return False
    else:
        sock.close()
        return True


def main() -> None:
    result = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "root_write_allowed": _write_probe(Path("/runtime-root-write-test")),
        "runner_root_write_allowed": _write_probe(Path("/opt/hermes/runners/runtime-write-test")),
        "tmp_write_allowed": _write_probe(Path("/tmp/runtime-write-test")),
        "run_write_allowed": _write_probe(Path("/run/runtime-write-test")),
        "state_write_allowed": _write_probe(Path("/var/tmp/hermes/runtime-write-test")),
        "cap_eff": _status_field("CapEff"),
        "no_new_privs": _status_field("NoNewPrivs"),
        "raw_socket_available": _raw_socket_available(),
        "tcp_socket_available": _tcp_socket_available(),
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
