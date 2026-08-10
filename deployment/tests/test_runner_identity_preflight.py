"""Repository-only tests for Runner runtime-promotion prerequisites.

Nothing here provisions a user, a group, a socket or a service. No privileged call is
made, no live host state is read and no canonical policy is mutated.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "deployment" / "runtime-promotion" / "runner_identity_preflight.py"
TEMPLATES = ROOT / "deployment" / "runtime-promotion" / "templates"
EXAMPLE = TEMPLATES / "runner-identity-descriptor.example.yaml"
TRANSPORT_POLICY = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"
ROUTING_POLICY = ROOT / "platform" / "runner-dispatch" / "routing-policy.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load("runner_identity_preflight_test", PREFLIGHT_PATH)


def _descriptor() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))


def _findings(descriptor: dict[str, Any]) -> list[str]:
    return list(preflight.run_preflight(descriptor).findings)


# ------------------------------------------------------- canonical state untouched


def test_canonical_transport_policy_remains_disabled_not_run() -> None:
    policy = yaml.safe_load(TRANSPORT_POLICY.read_text(encoding="utf-8"))
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["modes"]["unix-peer"]["socket_path"] == "NOT_CONFIGURED"
    assert policy["modes"]["unix-peer"]["allowed_peers"] == []


def test_canonical_routing_policy_remains_disabled_not_run() -> None:
    policy = yaml.safe_load(ROUTING_POLICY.read_text(encoding="utf-8"))
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["bindings"] == []


# ------------------------------------------------------------------ happy path


def test_example_descriptor_passes_and_stays_not_run() -> None:
    result = preflight.run_preflight(_descriptor())
    assert result.ok is True
    assert result.findings == ()
    assert result.rendered_transport_policy["runtime_status"] == "NOT_RUN"
    assert result.rendered_routing_policy["runtime_status"] == "NOT_RUN"
    assert result.rendered_transport_policy["execution_authority"] == "none"
    assert result.rendered_routing_policy["execution_authority"] == "none"


def test_cli_check_exits_zero_and_emits_json() -> None:
    assert preflight.main(["check"]) == preflight.EXIT_OK
    completed = subprocess.run(
        [sys.executable, str(PREFLIGHT_PATH), "--json", "check"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["runtime_status"] == "NOT_RUN"
    assert report["execution_authority"] == "none"


# --------------------------------------------------------------- identity rules


def test_root_gateway_identity_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["gateway"]["uid"] = 0
    assert any("uid must not be root" in f for f in _findings(descriptor))


def test_root_group_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["runner"]["gid"] = 0
    assert any("must not be the root group" in f for f in _findings(descriptor))


def test_shared_gateway_and_runner_uid_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["runner"]["uid"] = descriptor["identities"]["gateway"]["uid"]
    assert any("must not share a UID" in f for f in _findings(descriptor))


def test_generic_shared_account_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["gateway"]["user"] = "www-data"
    findings = _findings(descriptor)
    assert any("dedicated account" in f for f in findings)


def test_login_shell_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["runner"]["shell"] = "/bin/bash"
    assert any("nologin" in f for f in _findings(descriptor))


def test_gateway_must_be_in_the_dispatch_group() -> None:
    descriptor = _descriptor()
    descriptor["identities"]["dispatch_group"]["members"] = ["hexor-runner"]
    assert any("gateway account must be a member" in f for f in _findings(descriptor))


# ----------------------------------------------------------------- socket rules


@pytest.mark.parametrize("mode", ["0666", "0664", "0777", "0606"])
def test_world_accessible_socket_modes_are_refused(mode: str) -> None:
    descriptor = _descriptor()
    descriptor["socket"]["mode"] = mode
    assert any("world access bits are refused" in f for f in _findings(descriptor))


def test_setgid_socket_mode_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["mode"] = "2660"
    findings = _findings(descriptor)
    assert any("4-digit octal" in f or "setuid" in f for f in findings)


def test_socket_owner_must_be_the_runner_identity() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["owner_uid"] = descriptor["identities"]["gateway"]["uid"]
    assert any("must be the Runner identity" in f for f in _findings(descriptor))


def test_socket_group_must_be_the_shared_dispatch_group() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["group_gid"] = 9999
    assert any("shared dispatch group" in f for f in _findings(descriptor))


def test_socket_outside_runtime_directory_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["path"] = "/tmp/runner-dispatch.sock"
    descriptor["socket"]["directory"]["path"] = "/tmp"
    assert any("runtime directory" in f for f in _findings(descriptor))


def test_socket_must_live_inside_declared_directory() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["path"] = "/run/other/runner-dispatch.sock"
    assert any("inside socket.directory.path" in f for f in _findings(descriptor))


def test_loose_directory_mode_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["socket"]["directory"]["mode"] = "0755"
    assert any("socket.directory" in f for f in _findings(descriptor))


# --------------------------------------------------------------- template rules


def test_rendered_templates_pass_the_products_own_validators() -> None:
    result = preflight.run_preflight(_descriptor())
    assert preflight.transport_contract.validate_policy(result.rendered_transport_policy) == []
    assert preflight.router_contract.validate_routing_policy(result.rendered_routing_policy) == []


def test_rendered_transport_binds_exactly_the_declared_gateway_credentials() -> None:
    descriptor = _descriptor()
    result = preflight.run_preflight(descriptor)
    peers = result.rendered_transport_policy["modes"]["unix-peer"]["allowed_peers"]
    assert len(peers) == 1
    assert peers[0]["uid"] == descriptor["identities"]["gateway"]["uid"]
    assert peers[0]["gid"] == descriptor["identities"]["gateway"]["gid"]
    assert peers[0]["principal_id"] == descriptor["identities"]["gateway"]["principal_id"]
    assert peers[0]["purpose"] == "runner-dispatch"


def test_rendered_transport_keeps_mtls_future_and_unconfigured() -> None:
    mtls = preflight.run_preflight(_descriptor()).rendered_transport_policy["modes"]["mtls"]
    assert mtls["status"] == "FUTURE"
    assert mtls["trust_store"] == "NOT_CONFIGURED"


def test_routing_binding_principal_must_be_in_the_transport_allowlist() -> None:
    descriptor = _descriptor()
    rendered = preflight.run_preflight(descriptor)
    routing = copy.deepcopy(rendered.rendered_routing_policy)
    routing["bindings"][0]["principal_id"] = "hexor.some-other-principal"
    findings: list[str] = []
    preflight._check_rendered_routing(routing, rendered.rendered_transport_policy, findings)
    assert any("not in the transport allowlist" in f for f in findings)


def test_templates_never_promote_runtime_status() -> None:
    for template in (
        TEMPLATES / "runner-transport-policy.enabled.template.yaml",
        TEMPLATES / "runner-dispatch-routing-policy.enabled.template.yaml",
    ):
        raw = template.read_text(encoding="utf-8")
        assert "runtime_status: NOT_RUN" in raw
        assert "execution_authority: none" in raw
        assert "RUNNING" not in raw
        assert "PROMOTED" not in raw


# ---------------------------------------------------------------- descriptor guards


def test_descriptor_runtime_status_cannot_claim_promotion() -> None:
    descriptor = _descriptor()
    descriptor["runtime_status"] = "RUNNING"
    assert any("must remain NOT_RUN" in f for f in _findings(descriptor))


def test_unknown_descriptor_fields_fail_closed() -> None:
    descriptor = _descriptor()
    descriptor["enable_now"] = True
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.run_preflight(descriptor)
    assert exc.value.code == "DESCRIPTOR_INVALID"


def test_unreadable_descriptor_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.load_descriptor(tmp_path / "missing.yaml")
    assert exc.value.code == "DESCRIPTOR_UNREADABLE"


def test_failing_descriptor_exits_fail_closed(tmp_path: Path) -> None:
    descriptor = _descriptor()
    descriptor["identities"]["gateway"]["uid"] = 0
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    assert preflight.main(["--descriptor", str(path), "check"]) == preflight.EXIT_FAIL_CLOSED


def test_preflight_performs_no_privileged_or_provisioning_calls() -> None:
    """AST-level proof: no provisioning import and no privileged/socket call."""

    tree = ast.parse(PREFLIGHT_PATH.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "pwd", "grp", "ctypes", "os"}

    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(ast.unparse(node.func))
    for forbidden in ("os.chown", "os.chmod", "os.setuid", "os.system", "subprocess.run"):
        assert forbidden not in called
