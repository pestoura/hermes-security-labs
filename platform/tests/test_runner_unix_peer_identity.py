from __future__ import annotations

import ast
import importlib.util
import os
import socket
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
POLICY_PATH = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("runner_unix_peer_identity_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity = _load()


def _enabled_policy(*, uid: int | None = None, gid: int | None = None):
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.transport.identity",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "modes": {
            "unix-peer": {
                "status": "CANDIDATE",
                "identity_source": "linux-so-peercred",
                "socket_path": "/run/hex0r-test/runner.sock",
                "allowed_peers": [
                    {
                        "principal_id": "hexor.execution-gateway",
                        "uid": os.getuid() if uid is None else uid,
                        "gid": os.getgid() if gid is None else gid,
                        "purpose": "runner-dispatch",
                    }
                ],
            },
            "mtls": {
                "status": "FUTURE",
                "identity_source": "x509-client-certificate",
                "trust_store": "NOT_CONFIGURED",
            },
        },
    }


def test_committed_policy_is_valid_disabled_and_deny_all() -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    assert identity.validate_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["modes"]["unix-peer"]["allowed_peers"] == []
    assert policy["modes"]["mtls"]["status"] == "FUTURE"


def test_cli_validates_committed_fail_closed_policy() -> None:
    assert identity.main(["validate"]) == 0


def test_disabled_policy_refuses_before_peer_authentication() -> None:
    policy = identity.load_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(identity.TransportIdentityError) as exc:
            identity.authenticate_unix_peer(left, policy)
        assert exc.value.code == "TRANSPORT_DISABLED"
    finally:
        left.close()
        right.close()


def test_kernel_peer_credentials_authenticate_exact_uid_gid_mapping() -> None:
    policy = _enabled_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = identity.authenticate_unix_peer(left, policy)
    finally:
        left.close()
        right.close()

    assert peer.principal_id == "hexor.execution-gateway"
    assert peer.purpose == "runner-dispatch"
    assert peer.transport == "unix-peer"
    assert peer.peer_uid == os.getuid()
    assert peer.peer_gid == os.getgid()
    assert peer.peer_pid > 0
    assert peer.evidence_source == "kernel-so-peercred"
    assert "peer_pid" not in peer.as_safe_dict()


def test_wrong_uid_is_denied_even_with_valid_unix_socket() -> None:
    policy = _enabled_policy(uid=os.getuid() + 100000)
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(identity.TransportIdentityError) as exc:
            identity.authenticate_unix_peer(left, policy)
        assert exc.value.code == "PEER_NOT_AUTHORIZED"
    finally:
        left.close()
        right.close()


def test_non_unix_socket_cannot_supply_peer_identity() -> None:
    policy = _enabled_policy()
    internet_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(identity.TransportIdentityError) as exc:
            identity.authenticate_unix_peer(internet_socket, policy)
        assert exc.value.code == "TRANSPORT_NOT_UNIX"
    finally:
        internet_socket.close()


def test_enabled_policy_requires_absolute_socket_path() -> None:
    policy = _enabled_policy()
    policy["modes"]["unix-peer"]["socket_path"] = "relative.sock"
    findings = identity.validate_policy(policy)
    assert any("socket_path must be absolute" in item for item in findings)


def test_duplicate_uid_gid_mapping_is_invalid() -> None:
    policy = _enabled_policy()
    duplicate = dict(policy["modes"]["unix-peer"]["allowed_peers"][0])
    duplicate["principal_id"] = "hexor.other-gateway"
    policy["modes"]["unix-peer"]["allowed_peers"].append(duplicate)
    findings = identity.validate_policy(policy)
    assert any("duplicate UID/GID mapping" in item for item in findings)


def test_duplicate_principal_is_invalid() -> None:
    policy = _enabled_policy()
    duplicate = dict(policy["modes"]["unix-peer"]["allowed_peers"][0])
    duplicate["uid"] += 1
    policy["modes"]["unix-peer"]["allowed_peers"].append(duplicate)
    findings = identity.validate_policy(policy)
    assert any("duplicate principal_id" in item for item in findings)


def test_wildcard_or_string_uid_is_invalid() -> None:
    policy = _enabled_policy()
    policy["modes"]["unix-peer"]["allowed_peers"][0]["uid"] = "*"
    findings = identity.validate_policy(policy)
    assert any("uid must be a non-negative integer" in item for item in findings)


def test_transport_identity_never_claims_execution_authority() -> None:
    policy = _enabled_policy()
    policy["execution_authority"] = "runner"
    findings = identity.validate_policy(policy)
    assert any("never claim execution authority" in item for item in findings)


def test_runtime_ready_claim_is_rejected() -> None:
    policy = _enabled_policy()
    policy["runtime_status"] = "READY"
    findings = identity.validate_policy(policy)
    assert any("runtime_status must remain NOT_RUN" in item for item in findings)


def test_mtls_cannot_be_silently_enabled_in_unix_peer_lane() -> None:
    policy = _enabled_policy()
    policy["modes"]["mtls"]["status"] = "CANDIDATE"
    policy["modes"]["mtls"]["trust_store"] = "/etc/hex0r/ca.pem"
    findings = identity.validate_policy(policy)
    assert any("mTLS transport must remain FUTURE" in item for item in findings)
    assert any("trust_store must remain NOT_CONFIGURED" in item for item in findings)


def test_identity_is_derived_from_socket_not_caller_supplied_credentials() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    authenticate = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "authenticate_unix_peer"
    )
    assert [arg.arg for arg in authenticate.args.args] == ["peer_socket", "policy"]
    assert "uid" not in [arg.arg for arg in authenticate.args.args]
    assert "gid" not in [arg.arg for arg in authenticate.args.args]
    assert "principal_id" not in [arg.arg for arg in authenticate.args.args]
