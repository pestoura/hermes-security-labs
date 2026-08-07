from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_BASE = ROOT / "platform" / "runtime-base"

spec = importlib.util.spec_from_file_location("runtime_policy", RUNTIME_BASE / "runtime_policy.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RuntimePolicyError = module.RuntimePolicyError
validate_runtime_policy = module.validate_runtime_policy
validate_runtime_request = module.validate_runtime_request


def _policy():
    return yaml.safe_load((RUNTIME_BASE / "runtime-base-policy.yaml").read_text())


def test_canonical_runtime_policy_passes() -> None:
    validate_runtime_policy(_policy())


def test_core_runtime_is_non_root_read_only_and_socket_free() -> None:
    policy = _policy()
    assert policy["runtime_user"]["required_non_root"] is True
    assert policy["runtime_user"]["allow_uid_zero"] is False
    assert policy["filesystem"]["root_filesystem"] == "read_only"
    assert policy["filesystem"]["docker_socket_allowed"] is False
    assert policy["filesystem"]["host_mounts_allowed"] is False


def test_runner_root_is_immutable_and_writable_paths_are_bounded() -> None:
    policy = _policy()
    assert policy["runner_layout"]["root"] == "/opt/hermes/runners"
    assert policy["runner_layout"]["immutable_code"] is True
    assert "/opt/hermes/runners" not in policy["filesystem"]["writable_paths"]
    assert set(policy["filesystem"]["writable_paths"]) <= {"/tmp", "/run", "/var/tmp/hermes"}


def test_core_profile_adds_no_linux_capabilities_and_defaults_to_tcp_connect() -> None:
    core = _policy()["capabilities"]["profiles"]["core"]
    assert core["add"] == []
    assert core["nmap_default_mode"] == "-sT"


def test_raw_network_profile_is_explicit_and_net_raw_only() -> None:
    raw = _policy()["capabilities"]["profiles"]["raw-network"]
    assert raw["add"] == ["NET_RAW"]
    assert raw["requires_explicit_profile"] is True
    assert raw["requires_justification"] is True


@pytest.mark.parametrize("field", ["command", "argv", "cwd", "environment", "shell", "executable"])
def test_request_cannot_shape_executable(field: str) -> None:
    with pytest.raises(RuntimePolicyError):
        validate_runtime_request({field: "synthetic"}, profile="core")


def test_raw_network_request_requires_justification() -> None:
    with pytest.raises(RuntimePolicyError):
        validate_runtime_request({}, profile="raw-network")
    validate_runtime_request({"capability_justification": "synthetic conformance case"}, profile="raw-network")


def test_policy_fails_closed_if_privileged_mode_is_enabled() -> None:
    policy = _policy()
    policy["capabilities"]["profiles"]["privileged"]["allowed"] = True
    with pytest.raises(RuntimePolicyError):
        validate_runtime_policy(policy)


def test_policy_fails_closed_on_unexpected_writable_path() -> None:
    policy = _policy()
    policy["filesystem"]["writable_paths"].append("/etc")
    with pytest.raises(RuntimePolicyError):
        validate_runtime_policy(policy)


def test_runtime_observations_remain_not_run() -> None:
    assert _policy()["runtime_status"] == {
        "image_build": "NOT_RUN",
        "container_start": "NOT_RUN",
        "non_root_observation": "NOT_RUN",
        "read_only_root_observation": "NOT_RUN",
        "capability_drop_observation": "NOT_RUN",
    }
