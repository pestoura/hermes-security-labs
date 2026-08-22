#!/usr/bin/env python3
"""Fail-closed deployment controller for the receipt-delivery runtime boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
DESCRIPTOR_PATH = HERE / "receipt-delivery-runtime.yaml"
LISTENER_SRC = HERE / "receipt_delivery_listener.py"
PEER_MODULE_SRC = REPO_ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
SOCKET_UNIT_SRC = HERE / "systemd" / "hexor-runner-authz.socket"
SERVICE_UNIT_SRC = HERE / "systemd" / "hexor-runner-authz.service"

INSTALL_DIR = Path("/opt/hexor/receipt-delivery-runtime")
SYSTEMD_DIR = Path("/etc/systemd/system")
LISTENER_DST = INSTALL_DIR / "receipt_delivery_listener.py"
PEER_MODULE_DST = INSTALL_DIR / "unix_peer_identity.py"
DESCRIPTOR_DST = INSTALL_DIR / "receipt-delivery-runtime.yaml"
SOCKET_UNIT_DST = SYSTEMD_DIR / "hexor-runner-authz.socket"
SERVICE_UNIT_DST = SYSTEMD_DIR / "hexor-runner-authz.service"
RUNTIME_DIR = Path("/run/hexor")
SOCKET_PATH = RUNTIME_DIR / "runner-authz.sock"


class ReceiptDeliveryDeploymentError(ValueError):
    """Stable fail-closed deployment error."""


@dataclass(frozen=True)
class DeploymentPlan:
    ok: bool
    findings: tuple[str, ...]
    install_files: tuple[tuple[Path, Path], ...]
    safe_state: dict[str, Any]


def load_descriptor(path: Path | str = DESCRIPTOR_PATH) -> dict[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReceiptDeliveryDeploymentError("descriptor unreadable or invalid") from exc
    if not isinstance(document, Mapping):
        raise ReceiptDeliveryDeploymentError("descriptor must be an object")
    return dict(document)


def _validate_descriptor(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN")
    if document.get("promotion_allowed") is not False:
        findings.append("promotion_allowed must remain false")
    if document.get("execution_authority") != "none":
        findings.append("execution_authority must remain none")

    socket_cfg = document.get("socket")
    expected_socket = {
        "path": "/run/hexor/runner-authz.sock",
        "owner_uid": 4101,
        "group_gid": 4110,
        "mode": "0660",
    }
    if not isinstance(socket_cfg, Mapping) or dict(socket_cfg) != expected_socket:
        findings.append("socket contract must match dedicated runner-authz boundary")

    peer = document.get("peer")
    if not isinstance(peer, Mapping):
        findings.append("peer contract is required")
    else:
        if peer.get("allowed_uid") != 4100:
            findings.append("peer.allowed_uid must be hexor-gateway uid 4100")
        if peer.get("identity_source") != "linux-so-peercred":
            findings.append("peer.identity_source must be linux-so-peercred")

    for section in ("receipt_delivery", "resolver"):
        value = document.get(section)
        if not isinstance(value, Mapping) or value.get("state") != "DISABLED":
            findings.append(f"{section}.state must remain DISABLED")
    effects = document.get("target_effects")
    if not isinstance(effects, Mapping) or any(v != "none" for v in effects.values()):
        findings.append("target_effects must remain none")
    return findings


def build_plan(document: Mapping[str, Any]) -> DeploymentPlan:
    findings = _validate_descriptor(document)
    install_files = (
        (LISTENER_SRC, LISTENER_DST),
        (PEER_MODULE_SRC, PEER_MODULE_DST),
        (DESCRIPTOR_PATH, DESCRIPTOR_DST),
        (SOCKET_UNIT_SRC, SOCKET_UNIT_DST),
        (SERVICE_UNIT_SRC, SERVICE_UNIT_DST),
    )
    safe_state = {
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "promotion_allowed": False,
        "receipt_delivery": "DISABLED",
        "resolver": "DISABLED",
        "target_effect": "none",
    }
    return DeploymentPlan(
        ok=not findings,
        findings=tuple(findings),
        install_files=install_files,
        safe_state=safe_state,
    )


import os
import shutil
import subprocess


def _default_command_runner(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    detail = (completed.stderr or completed.stdout or "").strip()
    return completed.returncode, detail


def _assert_installable(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise ReceiptDeliveryDeploymentError(f"required source artifact missing: {src}")
    if not dst.exists():
        return
    if dst.is_symlink() or not dst.is_file():
        raise ReceiptDeliveryDeploymentError(f"installed artifact drift: {dst}")
    if dst.read_bytes() != src.read_bytes():
        raise ReceiptDeliveryDeploymentError(f"installed artifact drift: {dst}")


def _install_file(src: Path, dst: Path, *, executable: bool) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o755 if executable else 0o644)


def _run_checked(runner: Any, command: list[str]) -> None:
    rc, _detail = runner(command)
    if rc != 0:
        raise ReceiptDeliveryDeploymentError(
            f"runtime lifecycle command failed safely: {command[0]}"
        )


def install_runtime(
    document: Mapping[str, Any],
    *,
    live: bool,
    require_root: bool = True,
    run_command: Any = None,
    identity_probe: Any = None,
) -> dict[str, Any]:
    plan = build_plan(document)
    if not plan.ok:
        raise ReceiptDeliveryDeploymentError("; ".join(plan.findings))
    if not live:
        return {"live": False, "safe_state": dict(plan.safe_state)}
    if require_root and os.geteuid() != 0:
        raise ReceiptDeliveryDeploymentError("root required for live install")

    identity_findings = (identity_probe or host_identity_findings)()
    if identity_findings:
        raise ReceiptDeliveryDeploymentError("; ".join(identity_findings))

    # Verify every source/destination before the first mutation.
    for src, dst in plan.install_files:
        _assert_installable(src, dst)

    for src, dst in plan.install_files:
        _install_file(src, dst, executable=(dst == LISTENER_DST))

    runner = run_command or _default_command_runner
    _run_checked(runner, ["systemctl", "daemon-reload"])
    _run_checked(
        runner,
        ["systemctl", "enable", "--now", "hexor-runner-authz.socket"],
    )
    return {
        "live": True,
        **dict(plan.safe_state),
        "socket": str(SOCKET_PATH),
        "activated_unit": "hexor-runner-authz.socket",
        "dispatch_changed": False,
    }


import grp
import pwd


def host_identity_findings() -> list[str]:
    findings: list[str] = []
    try:
        gateway = pwd.getpwuid(4100)
        runner = pwd.getpwuid(4101)
        dispatch = grp.getgrgid(4110)
    except KeyError:
        return ["canonical receipt-delivery identities are incomplete"]
    if gateway.pw_name != "hexor-gateway" or gateway.pw_gid != 4100:
        findings.append("hexor-gateway uid/gid contract mismatch")
    if runner.pw_name != "hexor-runner" or runner.pw_gid != 4101:
        findings.append("hexor-runner uid/gid contract mismatch")
    if dispatch.gr_name != "hexor-dispatch":
        findings.append("hexor-dispatch gid contract mismatch")
    members = set(dispatch.gr_mem)
    if not {"hexor-gateway", "hexor-runner"}.issubset(members):
        findings.append("hexor-dispatch membership contract mismatch")
    return findings


def rollback_runtime(
    document: Mapping[str, Any],
    *,
    live: bool,
    require_root: bool = True,
    run_command: Any = None,
) -> dict[str, Any]:
    plan = build_plan(document)
    if not plan.ok:
        raise ReceiptDeliveryDeploymentError("; ".join(plan.findings))
    if not live:
        return {
            "live": False,
            "would_remove": [str(dst) for _src, dst in plan.install_files if dst.exists()],
            "preserves_identities": True,
            "dispatch_changed": False,
        }
    if require_root and os.geteuid() != 0:
        raise ReceiptDeliveryDeploymentError("root required for live rollback")

    # Prove every existing owned artifact is still canonical before removal.
    for src, dst in plan.install_files:
        if dst.exists():
            _assert_installable(src, dst)

    runner = run_command or _default_command_runner
    _run_checked(
        runner,
        ["systemctl", "disable", "--now", "hexor-runner-authz.socket"],
    )
    _run_checked(
        runner,
        ["systemctl", "disable", "--now", "hexor-runner-authz.service"],
    )
    removed: list[str] = []
    for _src, dst in plan.install_files:
        if dst.exists():
            dst.unlink()
            removed.append(str(dst))
    if INSTALL_DIR.exists() and not any(INSTALL_DIR.iterdir()):
        INSTALL_DIR.rmdir()
    _run_checked(runner, ["systemctl", "daemon-reload"])
    return {
        "live": True,
        "removed": removed,
        "preserves_identities": True,
        "preserves_runtime_directory": True,
        "dispatch_changed": False,
    }


import argparse
import json
import sys
from collections.abc import Sequence


def _plan_payload(plan: DeploymentPlan) -> dict[str, Any]:
    return {
        "ok": plan.ok,
        "findings": list(plan.findings),
        "install_files": [[str(src), str(dst)] for src, dst in plan.install_files],
        "safe_state": dict(plan.safe_state),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--descriptor", default=str(DESCRIPTOR_PATH))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    install = sub.add_parser("install-runtime")
    install.add_argument("--live", action="store_true")
    rollback = sub.add_parser("rollback-runtime")
    rollback.add_argument("--live", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        descriptor = load_descriptor(args.descriptor)
        if args.command == "plan":
            plan = build_plan(descriptor)
            if not plan.ok:
                raise ReceiptDeliveryDeploymentError("deployment plan refused")
            print(json.dumps(_plan_payload(plan), sort_keys=True))
            return 0
        if args.command == "install-runtime":
            result = install_runtime(descriptor, live=bool(args.live))
        else:
            result = rollback_runtime(descriptor, live=bool(args.live))
        print(json.dumps(result, sort_keys=True))
        return 0
    except ReceiptDeliveryDeploymentError:
        print(
            json.dumps({"ok": False, "code": "DEPLOYMENT_REFUSED"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
