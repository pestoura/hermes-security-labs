#!/usr/bin/env python3
"""Read-only preflight for Runner runtime-promotion prerequisites.

This validator answers a deployment question, not a runtime one: *would the declared
operating-system identities, AF_UNIX socket ownership/mode and rendered transport/routing
policies be acceptable if someone later decided to promote the Runner channel?*

It never provisions anything. It creates no user, no group, no socket and no service; it
does not read the live host, does not require privileges, does not mutate any canonical
policy and does not change ``runtime_status``. Rendered templates deliberately keep
``runtime_status: NOT_RUN`` so that rendering is still not promotion.

Rendered policies are handed to the product's own canonical validators so a template that
the product would reject cannot pass here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import string
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEMPLATES = HERE / "templates"
TRANSPORT_TEMPLATE = TEMPLATES / "runner-transport-policy.enabled.template.yaml"
ROUTING_TEMPLATE = TEMPLATES / "runner-dispatch-routing-policy.enabled.template.yaml"
EXAMPLE_DESCRIPTOR = TEMPLATES / "runner-identity-descriptor.example.yaml"

TRANSPORT_MODULE_PATH = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
ROUTER_MODULE_PATH = ROOT / "platform" / "runner-dispatch" / "router.py"

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2

PRINCIPAL_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
MODE_RE = re.compile(r"^0[0-7]{3}$")
NOLOGIN_SHELLS = {
    "/usr/sbin/nologin",
    "/sbin/nologin",
    "/usr/bin/nologin",
    "/bin/false",
    "/usr/bin/false",
}
RUNTIME_DIR_PREFIXES = ("/run/", "/var/run/")
GENERIC_ACCOUNTS = {"root", "nobody", "daemon", "www-data", "ubuntu", "admin"}

IDENTITY_FIELDS = {"principal_id", "user", "uid", "gid", "shell"}
GROUP_FIELDS = {"group", "gid", "members"}
SOCKET_FIELDS = {"path", "owner_uid", "group_gid", "mode", "directory"}
DIRECTORY_FIELDS = {"path", "owner_uid", "group_gid", "mode"}
ROUTING_FIELDS = {"adapter_id", "target_id", "capability_id"}
DESCRIPTOR_FIELDS = {"schema_version", "descriptor_id", "runtime_status", "identities", "socket", "routing"}


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNNER_SDK_SRC = ROOT / "platform" / "runner-protocol" / "src"
if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(RUNNER_SDK_SRC))

transport_contract = _load_module("runtime_promotion_transport_contract", TRANSPORT_MODULE_PATH)
router_contract = _load_module("runtime_promotion_router_contract", ROUTER_MODULE_PATH)


class PreflightError(ValueError):
    """Fail-closed preflight error carrying a stable refusal code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    findings: tuple[str, ...]
    rendered_transport_policy: dict[str, Any]
    rendered_routing_policy: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": list(self.findings),
            "runtime_status": "NOT_RUN",
            "execution_authority": "none",
            "rendered_transport_policy": self.rendered_transport_policy,
            "rendered_routing_policy": self.rendered_routing_policy,
        }


def _is_uid(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def load_descriptor(path: Path | str) -> dict[str, Any]:
    descriptor_path = Path(path)
    try:
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PreflightError("DESCRIPTOR_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise PreflightError("DESCRIPTOR_INVALID", str(exc)) from exc
    if not isinstance(document, Mapping):
        raise PreflightError("DESCRIPTOR_INVALID", "descriptor must be an object")
    return dict(document)


# ------------------------------------------------------------------ identities


def _check_identity(role: str, identity: Any, findings: list[str]) -> None:
    label = f"identities.{role}"
    if not isinstance(identity, Mapping) or set(identity) != IDENTITY_FIELDS:
        findings.append(f"{label}: exact fields {sorted(IDENTITY_FIELDS)} are required")
        return
    principal = identity.get("principal_id")
    user = identity.get("user")
    uid = identity.get("uid")
    gid = identity.get("gid")
    shell = identity.get("shell")

    if not isinstance(principal, str) or PRINCIPAL_RE.fullmatch(principal) is None:
        findings.append(f"{label}: principal_id is invalid")
    if not isinstance(user, str) or USER_RE.fullmatch(user) is None:
        findings.append(f"{label}: user is invalid")
    elif user in GENERIC_ACCOUNTS:
        findings.append(f"{label}: user must be a dedicated account, not {user}")
    if not _is_uid(uid):
        findings.append(f"{label}: uid must be a non-negative integer")
    elif uid == 0:
        findings.append(f"{label}: uid must not be root")
    if not _is_uid(gid):
        findings.append(f"{label}: gid must be a non-negative integer")
    elif gid == 0:
        findings.append(f"{label}: gid must not be the root group")
    if shell not in NOLOGIN_SHELLS:
        findings.append(f"{label}: shell must be a nologin/false shell")


def _check_identities(identities: Any, findings: list[str]) -> None:
    if not isinstance(identities, Mapping) or set(identities) != {"gateway", "runner", "dispatch_group"}:
        findings.append("identities: exact keys gateway, runner, dispatch_group are required")
        return

    _check_identity("gateway", identities.get("gateway"), findings)
    _check_identity("runner", identities.get("runner"), findings)

    gateway = identities.get("gateway")
    runner = identities.get("runner")
    if isinstance(gateway, Mapping) and isinstance(runner, Mapping):
        if gateway.get("uid") == runner.get("uid"):
            findings.append("identities: gateway and runner must not share a UID")
        if gateway.get("user") == runner.get("user"):
            findings.append("identities: gateway and runner must not share an account")
        if gateway.get("principal_id") == runner.get("principal_id"):
            findings.append("identities: gateway and runner must not share a principal_id")

    group = identities.get("dispatch_group")
    if not isinstance(group, Mapping) or set(group) != GROUP_FIELDS:
        findings.append(f"identities.dispatch_group: exact fields {sorted(GROUP_FIELDS)} are required")
        return
    group_gid = group.get("gid")
    if not _is_uid(group_gid):
        findings.append("identities.dispatch_group: gid must be a non-negative integer")
    elif group_gid == 0:
        findings.append("identities.dispatch_group: gid must not be the root group")
    members = group.get("members")
    if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
        findings.append("identities.dispatch_group: members must be an array of account names")
        return
    if isinstance(gateway, Mapping) and gateway.get("user") not in members:
        findings.append("identities.dispatch_group: gateway account must be a member")
    if isinstance(runner, Mapping) and runner.get("user") not in members:
        findings.append("identities.dispatch_group: runner account must be a member")


# ---------------------------------------------------------------------- socket


def _check_mode(label: str, value: Any, *, maximum: int, findings: list[str]) -> None:
    if not isinstance(value, str) or MODE_RE.fullmatch(value) is None:
        findings.append(f"{label}: mode must be a 4-digit octal string such as '0660'")
        return
    mode = int(value, 8)
    if mode & 0o7000:
        findings.append(f"{label}: setuid/setgid/sticky bits are refused")
    if mode & 0o007:
        findings.append(f"{label}: world access bits are refused")
    if mode & ~maximum:
        findings.append(f"{label}: mode must be {oct(maximum)} or tighter")


def _check_socket(socket_declaration: Any, identities: Any, findings: list[str]) -> None:
    if not isinstance(socket_declaration, Mapping) or set(socket_declaration) != SOCKET_FIELDS:
        findings.append(f"socket: exact fields {sorted(SOCKET_FIELDS)} are required")
        return

    path = socket_declaration.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        findings.append("socket.path must be absolute")
    elif not path.startswith(RUNTIME_DIR_PREFIXES):
        findings.append("socket.path must live under a runtime directory (/run or /var/run)")

    runner = identities.get("runner") if isinstance(identities, Mapping) else None
    group = identities.get("dispatch_group") if isinstance(identities, Mapping) else None
    runner_uid = runner.get("uid") if isinstance(runner, Mapping) else None
    group_gid = group.get("gid") if isinstance(group, Mapping) else None

    owner_uid = socket_declaration.get("owner_uid")
    if not _is_uid(owner_uid):
        findings.append("socket.owner_uid must be a non-negative integer")
    elif owner_uid == 0:
        findings.append("socket.owner_uid must not be root")
    elif runner_uid is not None and owner_uid != runner_uid:
        findings.append("socket.owner_uid must be the Runner identity that binds the socket")

    socket_gid = socket_declaration.get("group_gid")
    if not _is_uid(socket_gid):
        findings.append("socket.group_gid must be a non-negative integer")
    elif socket_gid == 0:
        findings.append("socket.group_gid must not be the root group")
    elif group_gid is not None and socket_gid != group_gid:
        findings.append("socket.group_gid must be the shared dispatch group")

    _check_mode("socket", socket_declaration.get("mode"), maximum=0o660, findings=findings)

    directory = socket_declaration.get("directory")
    if not isinstance(directory, Mapping) or set(directory) != DIRECTORY_FIELDS:
        findings.append(f"socket.directory: exact fields {sorted(DIRECTORY_FIELDS)} are required")
        return
    dir_path = directory.get("path")
    if not isinstance(dir_path, str) or not dir_path.startswith("/"):
        findings.append("socket.directory.path must be absolute")
    elif isinstance(path, str) and not path.startswith(dir_path.rstrip("/") + "/"):
        findings.append("socket.path must live inside socket.directory.path")
    dir_owner = directory.get("owner_uid")
    if not _is_uid(dir_owner) or dir_owner == 0:
        findings.append("socket.directory.owner_uid must be a non-root uid")
    elif runner_uid is not None and dir_owner != runner_uid:
        findings.append("socket.directory.owner_uid must be the Runner identity")
    dir_gid = directory.get("group_gid")
    if not _is_uid(dir_gid) or dir_gid == 0:
        findings.append("socket.directory.group_gid must be a non-root gid")
    elif group_gid is not None and dir_gid != group_gid:
        findings.append("socket.directory.group_gid must be the shared dispatch group")
    _check_mode("socket.directory", directory.get("mode"), maximum=0o750, findings=findings)


# ------------------------------------------------------------------- templates


def render_template(path: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    """Substitute descriptor values into an inert policy template and parse it."""

    raw = path.read_text(encoding="utf-8")
    try:
        rendered = string.Template(raw).substitute(values)
    except KeyError as exc:
        raise PreflightError("TEMPLATE_PLACEHOLDER_UNRESOLVED", f"missing value for {exc}") from exc
    document = yaml.safe_load(rendered)
    if not isinstance(document, Mapping):
        raise PreflightError("TEMPLATE_INVALID", f"{path.name} must render to an object")
    return dict(document)


def _check_rendered_transport(policy: Mapping[str, Any], findings: list[str]) -> None:
    findings.extend(f"transport template: {problem}" for problem in transport_contract.validate_policy(policy))
    if policy.get("state") != "ENABLED":
        findings.append("transport template: rendered state must be ENABLED")
    if policy.get("runtime_status") != "NOT_RUN":
        findings.append("transport template: rendering must not promote runtime_status")
    if policy.get("execution_authority") != "none":
        findings.append("transport template: execution_authority must remain none")
    if policy.get("default") != "deny":
        findings.append("transport template: default must remain deny")
    mtls = (policy.get("modes") or {}).get("mtls")
    if not isinstance(mtls, Mapping) or mtls.get("status") != "FUTURE" or mtls.get("trust_store") != "NOT_CONFIGURED":
        findings.append("transport template: mtls must remain FUTURE / NOT_CONFIGURED")


def _check_rendered_routing(
    policy: Mapping[str, Any], transport_policy: Mapping[str, Any], findings: list[str]
) -> None:
    findings.extend(f"routing template: {problem}" for problem in router_contract.validate_routing_policy(policy))
    if policy.get("state") != "ENABLED":
        findings.append("routing template: rendered state must be ENABLED")
    if policy.get("runtime_status") != "NOT_RUN":
        findings.append("routing template: rendering must not promote runtime_status")
    if policy.get("execution_authority") != "none":
        findings.append("routing template: execution_authority must remain none")
    if policy.get("default") != "deny":
        findings.append("routing template: default must remain deny")

    allowed = ((transport_policy.get("modes") or {}).get("unix-peer") or {}).get("allowed_peers")
    principals = {
        peer.get("principal_id")
        for peer in (allowed if isinstance(allowed, list) else [])
        if isinstance(peer, Mapping)
    }
    bindings = policy.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        findings.append("routing template: at least one binding is required")
        return
    for position, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            continue
        if binding.get("principal_id") not in principals:
            findings.append(
                f"routing template: bindings[{position}] principal is not in the transport allowlist"
            )


# --------------------------------------------------------------------- preflight


def run_preflight(descriptor: Mapping[str, Any]) -> PreflightResult:
    findings: list[str] = []

    if set(descriptor) != DESCRIPTOR_FIELDS:
        raise PreflightError(
            "DESCRIPTOR_INVALID",
            f"descriptor exact fields {sorted(DESCRIPTOR_FIELDS)} are required",
        )
    if descriptor.get("schema_version") != "1.0":
        findings.append("descriptor schema_version must be '1.0'")
    if descriptor.get("runtime_status") != "NOT_RUN":
        findings.append("descriptor runtime_status must remain NOT_RUN; this is not a promotion")

    identities = descriptor.get("identities")
    _check_identities(identities, findings)
    _check_socket(descriptor.get("socket"), identities, findings)

    routing = descriptor.get("routing")
    if not isinstance(routing, Mapping) or set(routing) != ROUTING_FIELDS:
        findings.append(f"routing: exact fields {sorted(ROUTING_FIELDS)} are required")
        routing = {}

    gateway = identities.get("gateway") if isinstance(identities, Mapping) else {}
    gateway = gateway if isinstance(gateway, Mapping) else {}
    socket_declaration = descriptor.get("socket")
    socket_declaration = socket_declaration if isinstance(socket_declaration, Mapping) else {}

    values = {
        "SOCKET_PATH": socket_declaration.get("path", ""),
        "GATEWAY_PRINCIPAL_ID": gateway.get("principal_id", ""),
        "GATEWAY_UID": gateway.get("uid", -1),
        "GATEWAY_GID": gateway.get("gid", -1),
        "ADAPTER_ID": routing.get("adapter_id", ""),
        "TARGET_ID": routing.get("target_id", ""),
        "CAPABILITY_ID": routing.get("capability_id", ""),
    }

    transport_policy = render_template(TRANSPORT_TEMPLATE, values)
    routing_policy = render_template(ROUTING_TEMPLATE, values)
    _check_rendered_transport(transport_policy, findings)
    _check_rendered_routing(routing_policy, transport_policy, findings)

    return PreflightResult(
        ok=not findings,
        findings=tuple(findings),
        rendered_transport_policy=transport_policy,
        rendered_routing_policy=routing_policy,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--descriptor", default=str(EXAMPLE_DESCRIPTOR))
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument("command", choices=("check",))
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        descriptor = load_descriptor(args.descriptor)
        result = run_preflight(descriptor)
    except PreflightError as exc:
        if args.json:
            print(json.dumps({"ok": False, "code": exc.code, "findings": [str(exc)]}, indent=2, sort_keys=True))
        else:
            print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    elif result.ok:
        print("OK runtime-promotion prerequisites are satisfied (runtime_status remains NOT_RUN)")
    else:
        for finding in result.findings:
            print(f"FAIL {finding}", file=sys.stderr)
    return EXIT_OK if result.ok else EXIT_FAIL_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
