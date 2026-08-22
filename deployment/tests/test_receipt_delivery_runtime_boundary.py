from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "deployment" / "receipt-delivery-runtime"
LISTENER = RUNTIME / "receipt_delivery_listener.py"
DEPLOYMENT = RUNTIME / "runtime_deployment.py"
DESCRIPTOR = RUNTIME / "receipt-delivery-runtime.yaml"
SOCKET_UNIT = RUNTIME / "systemd" / "hexor-runner-authz.socket"
SERVICE_UNIT = RUNTIME / "systemd" / "hexor-runner-authz.service"


def test_receipt_delivery_runtime_artifacts_and_socket_contract_exist() -> None:
    for path in (LISTENER, DEPLOYMENT, DESCRIPTOR, SOCKET_UNIT, SERVICE_UNIT):
        assert path.is_file(), path

    socket_unit = SOCKET_UNIT.read_text(encoding="utf-8")
    assert "ListenStream=/run/hexor/runner-authz.sock" in socket_unit
    assert "SocketUser=hexor-runner" in socket_unit
    assert "SocketGroup=hexor-dispatch" in socket_unit
    assert "SocketMode=0660" in socket_unit
    assert "Accept=no" in socket_unit

    service = SERVICE_UNIT.read_text(encoding="utf-8")
    assert "User=hexor-runner" in service
    assert "SupplementaryGroups=hexor-dispatch" in service
    assert "NoNewPrivileges=true" in service
    assert "RestrictAddressFamilies=AF_UNIX" in service

import importlib.util
import sys
from types import SimpleNamespace
from typing import Any

import pytest


def _load_listener() -> Any:
    spec = importlib.util.spec_from_file_location("chg088_receipt_listener_test", LISTENER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _NoPayloadReadSocket:
    def recv(self, _size: int) -> bytes:
        raise AssertionError("payload must not be read before authorization")

    def settimeout(self, _seconds: float) -> None:
        raise AssertionError("timeout must not be set before authorization")

def test_gateway_peer_identity_is_derived_from_kernel_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = _load_listener()
    assert hasattr(listener, "authenticate_gateway_peer")
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=71, uid=4100, gid=4100),
    )
    peer = listener.authenticate_gateway_peer(_NoPayloadReadSocket())
    assert peer == {"uid": 4100, "principal": "hexor.execution-gateway"}


def test_unauthorized_peer_is_refused_before_payload_read(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = _load_listener()
    assert hasattr(listener, "authenticate_gateway_peer")
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=72, uid=4999, gid=4999),
    )
    with pytest.raises(listener.ReceiptDeliveryRuntimeError) as exc_info:
        listener.authenticate_gateway_peer(_NoPayloadReadSocket())
    assert exc_info.value.code == "PEER_UID_UNAUTHORIZED"

def test_disabled_delivery_is_authenticated_hold_without_payload_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _load_listener()
    assert hasattr(listener, "handle_connection")
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=73, uid=4100, gid=4100),
    )
    outcome = listener.handle_connection(_NoPayloadReadSocket(), delivery=None)
    assert outcome.as_safe_dict() == {
        "status": "REFUSED",
        "code": "DELIVERY_DISABLED",
        "authorization_ref": None,
        "sequence": None,
        "duplicate": None,
    }

import json


class _FrameSocket:
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)
        self.timeout: float | None = None

    def settimeout(self, seconds: float) -> None:
        self.timeout = seconds

    def recv(self, _size: int) -> bytes:
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class _EnabledDelivery:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any], Any]] = []

    def deliver(self, envelope: dict[str, Any], *, peer: dict[str, Any], audit_context: Any = None) -> Any:
        self.calls.append((envelope, peer, audit_context))
        return SimpleNamespace(
            authorization_ref="tb1-authz:v1:" + "1" * 64,
            sequence=envelope["sequence"],
            accepted=True,
            duplicate=False,
        )

def test_enabled_delivery_reads_one_bounded_frame_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _load_listener()
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=74, uid=4100, gid=4100),
    )
    envelope = {
        "schema_version": "1.0",
        "issuer": "hermes-control-plane",
        "sequence": 7,
        "receipt": {"fixture": "public-test-value"},
    }
    sock = _FrameSocket(json.dumps(envelope).encode("utf-8") + b"\n")
    delivery = _EnabledDelivery()
    audit_context = {"campaign_id": "c", "run_id": "r"}

    outcome = listener.handle_connection(
        sock, delivery=delivery, audit_context=audit_context
    )
    assert sock.timeout == 2.0
    assert delivery.calls == [
        (envelope, {"uid": 4100, "principal": "hexor.execution-gateway"}, audit_context)
    ]
    assert outcome.status == "ACCEPTED"
    assert outcome.code == "RECEIPT_VERIFIED"
    assert outcome.sequence == 7
    assert outcome.duplicate is False
    assert outcome.authorization_ref == "tb1-authz:v1:" + "1" * 64

class _TimeoutFrameSocket(_FrameSocket):
    def recv(self, _size: int) -> bytes:
        raise TimeoutError("backend timeout detail must not escape")


def test_frame_timeout_is_a_sanitized_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = _load_listener()
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=75, uid=4100, gid=4100),
    )
    sock = _TimeoutFrameSocket()
    outcome = listener.handle_connection(sock, delivery=_EnabledDelivery())
    assert sock.timeout == 2.0
    assert outcome.as_safe_dict() == {
        "status": "REFUSED",
        "code": "FRAME_TIMEOUT",
        "authorization_ref": None,
        "sequence": None,
        "duplicate": None,
    }

class _UnsafeErrorDelivery(_EnabledDelivery):
    def deliver(self, envelope: dict[str, Any], *, peer: dict[str, Any], audit_context: Any = None) -> Any:
        exc = RuntimeError("sensitive backend detail")
        exc.code = "TOKEN=must-not-escape"  # type: ignore[attr-defined]
        raise exc


class _MalformedSuccessDelivery(_EnabledDelivery):
    def deliver(self, envelope: dict[str, Any], *, peer: dict[str, Any], audit_context: Any = None) -> Any:
        return SimpleNamespace(authorization_ref=None, sequence="seven", accepted=True, duplicate=False)


def _authorized_frame(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, _FrameSocket]:
    listener = _load_listener()
    monkeypatch.setattr(
        listener.peer_module,
        "read_kernel_peer_credentials",
        lambda _sock: SimpleNamespace(pid=76, uid=4100, gid=4100),
    )
    envelope = {"schema_version": "1.0", "issuer": "hermes-control-plane", "sequence": 7, "receipt": {}}
    return listener, _FrameSocket(json.dumps(envelope).encode() + b"\n")


def test_delegate_error_code_is_allowlisted_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    listener, sock = _authorized_frame(monkeypatch)
    outcome = listener.handle_connection(sock, delivery=_UnsafeErrorDelivery())
    assert outcome.status == "REFUSED"
    assert outcome.code == "DELIVERY_FAILED"


def test_malformed_delegate_success_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    listener, sock = _authorized_frame(monkeypatch)
    outcome = listener.handle_connection(sock, delivery=_MalformedSuccessDelivery())
    assert outcome.status == "REFUSED"
    assert outcome.code == "DELIVERY_RESULT_INVALID"

def test_listener_check_mode_is_read_only_and_reports_hold(capsys: pytest.CaptureFixture[str]) -> None:
    listener = _load_listener()
    assert hasattr(listener, "main")
    assert listener.main(["--check"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "socket_path": "/run/hexor/runner-authz.sock",
        "peer_uid": 4100,
        "peer_principal": "hexor.execution-gateway",
        "mode": "AUTHENTICATED_HOLD",
        "receipt_delivery": "DISABLED",
        "execution_authority": "NONE",
        "promotion_allowed": False,
    }


def test_live_serve_fails_closed_without_systemd_socket_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _load_listener()
    assert hasattr(listener, "serve_systemd_socket")
    monkeypatch.delenv("LISTEN_PID", raising=False)
    monkeypatch.delenv("LISTEN_FDS", raising=False)
    with pytest.raises(listener.ReceiptDeliveryRuntimeError) as exc_info:
        listener.serve_systemd_socket()
    assert exc_info.value.code == "SOCKET_ACTIVATION_MISSING"

def _load_deployment() -> Any:
    spec = importlib.util.spec_from_file_location("chg088_receipt_deployment_test", DEPLOYMENT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_deployment_plan_is_fail_closed_and_separate_from_dispatch() -> None:
    deployment = _load_deployment()
    assert hasattr(deployment, "load_descriptor")
    assert hasattr(deployment, "build_plan")
    descriptor = deployment.load_descriptor()
    plan = deployment.build_plan(descriptor)
    assert plan.ok is True
    destinations = {str(dst) for _src, dst in plan.install_files}
    assert "/opt/hexor/receipt-delivery-runtime/receipt_delivery_listener.py" in destinations
    assert "/opt/hexor/receipt-delivery-runtime/unix_peer_identity.py" in destinations
    assert "/etc/systemd/system/hexor-runner-authz.socket" in destinations
    assert "/etc/systemd/system/hexor-runner-authz.service" in destinations
    assert all("runner-dispatch.sock" not in item for item in destinations)
    assert plan.safe_state == {
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "promotion_allowed": False,
        "receipt_delivery": "DISABLED",
        "resolver": "DISABLED",
        "target_effect": "none",
    }


def _redirect_install_paths(monkeypatch: pytest.MonkeyPatch, deployment: Any, root: Path) -> None:
    install = root / "opt/hexor/receipt-delivery-runtime"
    systemd = root / "etc/systemd/system"
    monkeypatch.setattr(deployment, "INSTALL_DIR", install)
    monkeypatch.setattr(deployment, "LISTENER_DST", install / "receipt_delivery_listener.py")
    monkeypatch.setattr(deployment, "PEER_MODULE_DST", install / "unix_peer_identity.py")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", install / "receipt-delivery-runtime.yaml")
    monkeypatch.setattr(deployment, "SOCKET_UNIT_DST", systemd / "hexor-runner-authz.socket")
    monkeypatch.setattr(deployment, "SERVICE_UNIT_DST", systemd / "hexor-runner-authz.service")


def test_install_is_idempotent_and_activates_only_authz_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = _load_deployment()
    _redirect_install_paths(monkeypatch, deployment, tmp_path)
    commands: list[list[str]] = []
    def runner(cmd: list[str]) -> tuple[int, str]:
        commands.append(list(cmd))
        return 0, ""

    descriptor = deployment.load_descriptor()
    first = deployment.install_runtime(
        descriptor, live=True, require_root=False, run_command=runner, identity_probe=lambda: []
    )
    second = deployment.install_runtime(
        descriptor, live=True, require_root=False, run_command=runner, identity_probe=lambda: []
    )
    assert first["runtime_status"] == "NOT_RUN"
    assert second["runtime_status"] == "NOT_RUN"
    assert first["receipt_delivery"] == "DISABLED"
    assert first["resolver"] == "DISABLED"
    assert first["promotion_allowed"] is False
    assert commands.count(["systemctl", "enable", "--now", "hexor-runner-authz.socket"]) == 2
    assert all("runner-dispatch" not in " ".join(cmd) for cmd in commands)


def test_install_refuses_drift_before_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = _load_deployment()
    _redirect_install_paths(monkeypatch, deployment, tmp_path)
    deployment.LISTENER_DST.parent.mkdir(parents=True)
    deployment.LISTENER_DST.write_text("DRIFT", encoding="utf-8")
    with pytest.raises(deployment.ReceiptDeliveryDeploymentError):
        deployment.install_runtime(
            deployment.load_descriptor(), live=True, require_root=False,
            run_command=lambda _cmd: (0, ""), identity_probe=lambda: [],
        )
    assert deployment.LISTENER_DST.read_text(encoding="utf-8") == "DRIFT"


def test_identity_preflight_blocks_install_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = _load_deployment()
    _redirect_install_paths(monkeypatch, deployment, tmp_path)
    commands: list[list[str]] = []
    with pytest.raises(deployment.ReceiptDeliveryDeploymentError):
        deployment.install_runtime(
            deployment.load_descriptor(),
            live=True,
            require_root=False,
            run_command=lambda cmd: (commands.append(list(cmd)) or (0, "")),
            identity_probe=lambda: ["hexor-gateway uid 4100 missing"],
        )
    assert commands == []
    assert not deployment.INSTALL_DIR.exists()


def test_rollback_removes_only_owned_authz_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = _load_deployment()
    _redirect_install_paths(monkeypatch, deployment, tmp_path)
    commands: list[list[str]] = []
    def runner(cmd: list[str]) -> tuple[int, str]:
        commands.append(list(cmd))
        return 0, ""

    descriptor = deployment.load_descriptor()
    deployment.install_runtime(
        descriptor, live=True, require_root=False,
        run_command=runner, identity_probe=lambda: [],
    )
    result = deployment.rollback_runtime(
        descriptor, live=True, require_root=False, run_command=runner
    )
    assert result["preserves_identities"] is True
    assert result["dispatch_changed"] is False
    assert all(not dst.exists() for _src, dst in deployment.build_plan(descriptor).install_files)
    assert ["systemctl", "disable", "--now", "hexor-runner-authz.socket"] in commands


def test_rollback_refuses_drift_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = _load_deployment()
    _redirect_install_paths(monkeypatch, deployment, tmp_path)
    descriptor = deployment.load_descriptor()
    deployment.install_runtime(
        descriptor, live=True, require_root=False,
        run_command=lambda _cmd: (0, ""), identity_probe=lambda: [],
    )
    deployment.SERVICE_UNIT_DST.write_text("DRIFT", encoding="utf-8")
    with pytest.raises(deployment.ReceiptDeliveryDeploymentError):
        deployment.rollback_runtime(
            descriptor, live=True, require_root=False,
            run_command=lambda _cmd: (0, ""),
        )
    assert deployment.SERVICE_UNIT_DST.exists()


class _CanonicalLookingErrorDelivery:
    enabled = True

    def deliver(self, _envelope: Any, *, peer: Any, audit_context: Any = None) -> Any:
        error = RuntimeError("internal delivery detail")
        error.code = "DELIVERY_ISSUER_UNAUTHORIZED"  # type: ignore[attr-defined]
        raise error


def test_delegate_codes_are_not_reflected_on_runtime_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener, sock = _authorized_frame(monkeypatch)
    outcome = listener.handle_connection(sock, delivery=_CanonicalLookingErrorDelivery())
    assert outcome.status == "REFUSED"
    assert outcome.code == "DELIVERY_FAILED"


def test_deployment_cli_plan_is_read_only_and_safe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment = _load_deployment()
    assert hasattr(deployment, "main")
    assert deployment.main(["plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["safe_state"]["receipt_delivery"] == "DISABLED"
    assert payload["safe_state"]["resolver"] == "DISABLED"
    assert payload["safe_state"]["promotion_allowed"] is False


def test_deployment_cli_failure_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deployment = _load_deployment()
    bad = tmp_path / "invalid.yaml"
    bad.write_text("schema_version: '9.9'\n", encoding="utf-8")

    assert deployment.main(["--descriptor", str(bad), "plan"]) == 2
    stderr = capsys.readouterr().err
    assert json.loads(stderr) == {
        "ok": False,
        "code": "DEPLOYMENT_REFUSED",
    }
