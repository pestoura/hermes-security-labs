from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IMAGE = "docker.io/library/python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322"


def _load_attestation():
    name = "_hex0r_docker_reset_attestation"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / "reset_attestation.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot load reset attestation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


attestation = _load_attestation()


class ControlledDockerResetError(RuntimeError):
    pass


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=False,
    )
    if check and result.returncode != 0:
        raise ControlledDockerResetError(result.stderr.strip() or "controlled docker operation failed")
    return result


def _init_volume(volume: str) -> None:
    _run([
        "docker", "run", "--rm", "--network", "none",
        "--mount", f"type=volume,source={volume},target=/lab",
        "--entrypoint", "/bin/sh", IMAGE, "-c", "chown 10001:10001 /lab",
    ])


def _write_fixture(volume: str, network: str, *, mutate: bool = False) -> None:
    script = (
        "from pathlib import Path; "
        "p=Path('/lab'); "
        "(p/'config.json').write_text('{\"mode\":\"vulnerable\",\"version\":1}\\n'); "
        "(p/'seed.txt').write_text('controlled-fixture\\n'); "
    )
    if mutate:
        script += "(p/'seed.txt').write_text('mutated\\n'); (p/'runtime-drift.txt').write_text('drift\\n')"
    _run([
        "docker", "run", "--rm",
        "--network", network,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt", "no-new-privileges:true",
        "--user", "10001:10001",
        "--memory", "64m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=1m",
        "--mount", f"type=volume,source={volume},target=/lab",
        "--entrypoint", "python", IMAGE, "-c", script,
    ])


def _snapshot(volume: str, network: str) -> dict[str, Any]:
    script = (
        "import hashlib,json; from pathlib import Path; p=Path('/lab'); "
        "files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(p.iterdir()) if x.is_file()}; "
        "print(json.dumps({'lifecycle':'READY','fixture_files':files,'file_count':len(files)},sort_keys=True))"
    )
    result = _run([
        "docker", "run", "--rm",
        "--network", network,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt", "no-new-privileges:true",
        "--user", "10001:10001",
        "--memory", "64m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=1m",
        "--mount", f"type=volume,source={volume},target=/lab,readonly",
        "--entrypoint", "python", IMAGE, "-c", script,
    ])
    try:
        value = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ControlledDockerResetError("invalid controlled snapshot") from exc
    if not isinstance(value, dict):
        raise ControlledDockerResetError("invalid controlled snapshot")
    return value


def _resource_exists(kind: str, name: str) -> bool:
    return _run(["docker", kind, "inspect", name], check=False).returncode == 0


def run_controlled_docker_reset() -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:12]
    network = f"hex0r-i01-net-{suffix}"
    volume = f"hex0r-i01-vol-{suffix}"
    label = "hex0r.controlled-ci=svp2-i01"
    first: dict[str, Any] | None = None
    second: dict[str, Any] | None = None
    try:
        _run(["docker", "network", "create", "--internal", "--label", label, network])
        _run(["docker", "volume", "create", "--label", label, volume])
        _init_volume(volume)
        _write_fixture(volume, network)
        first = _snapshot(volume, network)

        _write_fixture(volume, network, mutate=True)
        drifted = _snapshot(volume, network)
        if drifted == first:
            raise ControlledDockerResetError("controlled drift was not introduced")

        _run(["docker", "volume", "rm", volume])
        _run(["docker", "volume", "create", "--label", label, volume])
        _init_volume(volume)
        _write_fixture(volume, network)
        second = _snapshot(volume, network)
        result = attestation.attest_reset_determinism([first, second])
        if result.deterministic is not True:
            raise ControlledDockerResetError("docker reset did not converge")
        canonical = result.canonical_sha256
    finally:
        _run(["docker", "volume", "rm", "-f", volume], check=False)
        _run(["docker", "network", "rm", network], check=False)

    residue = {
        "network_present": _resource_exists("network", network),
        "volume_present": _resource_exists("volume", volume),
    }
    if any(residue.values()):
        raise ControlledDockerResetError("controlled Docker residue remains")

    return {
        "schema_version": "1.0.0",
        "boundary": "CONTROLLED_CI_DOCKER",
        "image": IMAGE,
        "network_internal": True,
        "privileged": False,
        "host_network": False,
        "docker_socket_mounted": False,
        "host_mounts": False,
        "rootfs_read_only": True,
        "capabilities": "DROP_ALL",
        "no_new_privileges": True,
        "runtime_uid": 10001,
        "deterministic": True,
        "canonical_sha256": canonical,
        "cleanup_zero_residue": True,
        "residue": residue,
        "production_lab_runtime": "NOT_RUN",
    }


def main() -> int:
    result = run_controlled_docker_reset()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
