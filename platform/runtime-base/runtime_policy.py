from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping

FORBIDDEN_CAPABILITIES = {"SYS_ADMIN", "SYS_PTRACE", "DAC_OVERRIDE"}
FORBIDDEN_REQUEST_FIELDS = {"command", "argv", "cwd", "environment", "shell", "executable"}


class RuntimePolicyError(ValueError):
    """Fail-closed runtime-base policy violation."""


def validate_runtime_policy(policy: Mapping[str, Any]) -> None:
    user = policy.get("runtime_user", {})
    if user.get("required_non_root") is not True or user.get("allow_uid_zero") is not False:
        raise RuntimePolicyError("core runtime must require non-root execution")
    uid_minimum = user.get("uid_minimum")
    if not isinstance(uid_minimum, int) or uid_minimum < 10000:
        raise RuntimePolicyError("uid_minimum must be >= 10000")

    filesystem = policy.get("filesystem", {})
    if filesystem.get("root_filesystem") != "read_only":
        raise RuntimePolicyError("root filesystem must be read-only")
    if filesystem.get("host_mounts_allowed") is not False:
        raise RuntimePolicyError("host mounts must be forbidden")
    if filesystem.get("docker_socket_allowed") is not False:
        raise RuntimePolicyError("Docker socket must be forbidden")

    runner_root = PurePosixPath(str(filesystem.get("runner_root", "")))
    if runner_root != PurePosixPath("/opt/hermes/runners"):
        raise RuntimePolicyError("runner root must be canonical")

    writable = {PurePosixPath(str(path)) for path in filesystem.get("writable_paths", [])}
    allowed = {PurePosixPath("/tmp"), PurePosixPath("/run"), PurePosixPath("/var/tmp/hermes")}
    if not writable.issubset(allowed):
        raise RuntimePolicyError("unexpected writable path")
    if runner_root in writable:
        raise RuntimePolicyError("runner code root cannot be writable")

    capabilities = policy.get("capabilities", {})
    if capabilities.get("default_drop_all") is not True:
        raise RuntimePolicyError("capabilities must be dropped by default")
    profiles = capabilities.get("profiles", {})
    core = profiles.get("core", {})
    if core.get("add") not in ([], None):
        raise RuntimePolicyError("core profile cannot add capabilities")
    if core.get("nmap_default_mode") != "-sT":
        raise RuntimePolicyError("nmap must default to TCP connect scan")

    raw_profile = profiles.get("raw-network", {})
    raw_add = set(raw_profile.get("add", []))
    if raw_add != {"NET_RAW"}:
        raise RuntimePolicyError("raw-network may add NET_RAW only")
    if raw_profile.get("requires_explicit_profile") is not True:
        raise RuntimePolicyError("NET_RAW requires explicit profile")
    if raw_profile.get("requires_justification") is not True:
        raise RuntimePolicyError("NET_RAW requires justification")
    if raw_add & FORBIDDEN_CAPABILITIES:
        raise RuntimePolicyError("forbidden elevated capability")

    privileged = profiles.get("privileged", {})
    if privileged.get("allowed") is not False:
        raise RuntimePolicyError("privileged runtime is forbidden")

    layout = policy.get("runner_layout", {})
    if layout.get("root") != "/opt/hermes/runners":
        raise RuntimePolicyError("runner layout root mismatch")
    if layout.get("immutable_code") is not True:
        raise RuntimePolicyError("runner code must be immutable")
    if layout.get("executable_from_request_fields") is not False:
        raise RuntimePolicyError("request fields cannot shape executable selection")


def validate_runtime_request(request: Mapping[str, Any], *, profile: str) -> None:
    forbidden = FORBIDDEN_REQUEST_FIELDS.intersection(request)
    if forbidden:
        raise RuntimePolicyError(f"command-shaped fields forbidden: {sorted(forbidden)}")
    if profile not in {"core", "browser", "heavy-tools", "raw-network"}:
        raise RuntimePolicyError("unknown runtime profile")
    if profile == "raw-network" and not request.get("capability_justification"):
        raise RuntimePolicyError("raw-network requires capability justification")
