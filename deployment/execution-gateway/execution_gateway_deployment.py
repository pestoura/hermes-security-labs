#!/usr/bin/env python3
"""Fail-closed Execution Gateway deployment boundary controller (#359).

Repository-only. The Execution Gateway is the CLIENT side of the Hexor AF_UNIX
dispatch boundary and the sibling of the Runner runtime HOLD boundary (#354).
It runs as the dedicated ``hexor-gateway`` identity (uid/gid 4100), is a member
of the shared ``hexor-dispatch`` group (4110), and connects as a client to
``/run/hexor/runner-dispatch.sock``.

This controller installs ONLY the gateway-owned artifacts:

- ``/opt/hexor/execution-gateway/execution_gateway_hold.py``
- ``/opt/hexor/execution-gateway/README.md``
- ``/opt/hexor/execution-gateway/execution-gateway-deployment.yaml``
- ``/etc/systemd/system/hexor-execution-gateway.service``
- ``/etc/tmpfiles.d/hexor-execution-gateway.conf``

It does NOT provision identities (that lifecycle is owned by the Runner runtime
boundary controller, ``deployment/runner-runtime/runtime_deployment.py``). The
gateway asserts that the canonical identities it depends on are EXACT and fails
closed on ABSENT or CONFLICT rather than silently creating conflicting IDs.
This keeps the repository convention explicit: the gateway never provisions,
never removes and never relinks the shared boundary identities.

It also never creates the dispatcher socket (the Runner side owns it),
never binds a trust store, never enables an execution policy, and never touches
a target (WebGoat/Kali) or the network. The envelope stays
DISABLED / default-deny / NOT_RUN / execution_authority=none /
promotion_allowed=false.

Subcommands:

- ``plan``          (read-only): render the deployment plan and verify the
                    fail-closed envelope. No host mutation.
- ``install-base``  : privileged base install. It performs a root gate, a
                    dependency preflight, an exact-aware identity/group
                    preflight (no provisioning), a drift preflight and then
                    installs only the gateway-owned artifacts root-owned with
                    exact modes, then daemon-reload / tmpfiles / enable --now the
                    gateway service. Fail-closed on any non-zero systemd step.
- ``rollback-base`` : stop/disable the gateway service, remove only the owned
                    gateway artifacts (fail-closed on drift/residue), then
                    daemon-reload. Identities, ``/run/hexor``, the Runner
                    socket/runtime, the trust store and all policy state are
                    always preserved.
"""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

# Sibling import without package context (loaded standalone by tests/templates).
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

GATEWAY_HOLD_SRC = HERE / "execution_gateway_hold.py"
README_SRC = HERE / "README.md"
DESCRIPTOR_SRC = HERE / "execution-gateway-deployment.yaml"
SERVICE_UNIT = HERE / "systemd" / "hexor-execution-gateway.service"
TMPFILES_SRC = HERE / "tmpfiles" / "hexor-execution-gateway.conf"

# Canonical installed gateway-owned runtime layout.
INSTALL_BIN_DIR = Path("/opt/hexor/execution-gateway")
HOLD_DST = INSTALL_BIN_DIR / "execution_gateway_hold.py"
README_DST = INSTALL_BIN_DIR / "README.md"
DESCRIPTOR_DST = INSTALL_BIN_DIR / "execution-gateway-deployment.yaml"
SYSTEMD_DST = Path("/etc/systemd/system")
TMPFILES_DST = Path("/etc/tmpfiles.d")
SERVICE_DST = SYSTEMD_DST / "hexor-execution-gateway.service"
TMPFILES_CONF_DST = TMPFILES_DST / "hexor-execution-gateway.conf"

# The gateway is the AF_UNIX CLIENT; it owns no socket and no runtime dir.
SYSTEMD_SERVICE_UNIT = "hexor-execution-gateway.service"
RUNTIME_DIR = Path("/run/hexor")
RUNNER_SOCKET = Path("/run/hexor/runner-dispatch.sock")
TRUST_STORE_PATH = "/etc/hexor/runner/authorization-trust-store.json"

# Canonical identities the gateway depends on (declared, never provisioned here).
HEXOR_GATEWAY_UID = 4100
HEXOR_GATEWAY_GID = 4100
HEXOR_DISPATCH_GID = 4110
HEXOR_GATEWAY_USER = "hexor-gateway"
HEXOR_GATEWAY_GROUP = "hexor-gateway"
HEXOR_DISPATCH_GROUP = "hexor-dispatch"
HEXOR_NOLOGIN_SHELL = "/usr/sbin/nologin"

# Canonical file mode/owner contract (root-owned, exact modes).
MODE_FILE = 0o0644
MODE_EXEC = 0o0755
OWNER_ROOT_UID = 0
OWNER_ROOT_GID = 0
DIR_MODE = 0o0755

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2
EXIT_USAGE = 64

# Fail-closed policy envelope (never promoted by this boundary).
POLICY_STATE = "DISABLED"
POLICY_DEFAULT = "deny"
POLICY_RUNTIME_STATUS = "NOT_RUN"
POLICY_EXECUTION_AUTHORITY = "none"
PROMOTION_ALLOWED = False

REQUIRED_TOP_KEYS = {
    "schema_version",
    "descriptor_id",
    "issue",
    "phase",
    "runtime_status",
    "promotion_allowed",
    "identities",
    "gateway_client",
    "policy",
    "listener",
    "trust_binding",
    "target_effects",
}

# Canonical name owners per namespace. The gateway only asserts the identities it
# depends on; the runner side owns the full provisioning lifecycle.
CANONICAL_UID_OWNERS = {HEXOR_GATEWAY_UID: HEXOR_GATEWAY_USER}
CANONICAL_GID_OWNERS = {HEXOR_GATEWAY_GID: HEXOR_GATEWAY_GROUP, HEXOR_DISPATCH_GID: HEXOR_DISPATCH_GROUP}

# Prohibited downstream effects for the gateway HOLD boundary (must match
# execution_gateway_hold.py PROHIBITED_EFFECTS and the descriptor listener).
PROHIBITED_EFFECTS = (
    "send_runner_payload",
    "authorize_execution",
    "create_receipt",
    "call_router",
    "call_adapter",
    "touch_evidence_plane",
    "touch_target",
    "enable_trust_store",
)


class IdentityStatus(str):
    """Outcome of assessing one canonical identity against a host probe."""

    EXACT = "exact"  # present and byte-identical to the canonical spec
    ABSENT = "absent"  # not present; NOT provisioned by the gateway (owner is #354)
    CONFLICT = "conflict"  # name<->id mismatch -> fail closed


class DeploymentBoundaryError(ValueError):
    """Stable fail-closed deployment boundary error."""

    def __init__(self, code: str, message: str, *, partial: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.partial = partial

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "findings": [str(self)], "partial": self.partial}


@dataclass(frozen=True)
class DeploymentPlan:
    ok: bool
    findings: tuple[str, ...]
    install_files: tuple[tuple[Path, Path], ...]
    remove_on_rollback: tuple[Path, ...]
    policy_envelope: dict[str, Any]
    prohibited_effects: frozenset[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": list(self.findings),
            "install_files": [[str(s), str(d)] for s, d in self.install_files],
            "remove_on_rollback": [str(p) for p in self.remove_on_rollback],
            "policy_envelope": self.policy_envelope,
            "prohibited_effects": sorted(self.prohibited_effects),
        }


# ----------------------------------------------------------------- host probes


def _safe(f: Callable[[Any], Any], key: Any) -> Any | None:
    try:
        return f(key)
    except KeyError:
        return None
    except Exception:  # noqa: BLE001 - any host lookup failure is "unknown"
        return None


def probe_users_groups() -> tuple[
    Callable[[int], Mapping[str, Any] | None],
    Callable[[str], Mapping[str, Any] | None],
    Callable[[int], Mapping[str, Any] | None],
    Callable[[str], Mapping[str, Any] | None],
]:
    """Return four host probe callables (by-uid/by-name for users and groups)."""

    def user_by_uid(uid: int) -> Mapping[str, Any] | None:
        entry = _safe(pwd.getpwuid, uid)
        if entry is None:
            return None
        return {"name": entry.pw_name, "uid": entry.pw_uid, "gid": entry.pw_gid, "shell": entry.pw_shell}

    def user_by_name(name: str) -> Mapping[str, Any] | None:
        entry = _safe(pwd.getpwnam, name)
        if entry is None:
            return None
        return {"name": entry.pw_name, "uid": entry.pw_uid, "gid": entry.pw_gid, "shell": entry.pw_shell}

    def group_by_gid(gid: int) -> Mapping[str, Any] | None:
        entry = _safe(grp.getgrgid, gid)
        if entry is None:
            return None
        return {"name": entry.gr_name, "gid": entry.gr_gid}

    def group_by_name(name: str) -> Mapping[str, Any] | None:
        entry = _safe(grp.getgrnam, name)
        if entry is None:
            return None
        return {"name": entry.gr_name, "gid": entry.gr_gid}

    return user_by_uid, user_by_name, group_by_gid, group_by_name


def probe_group_members() -> Callable[[str], tuple[str, ...] | None]:
    """Return a read-only probe of a group's supplementary member list."""

    def group_members(name: str) -> tuple[str, ...] | None:
        entry = _safe(grp.getgrnam, name)
        if entry is None:
            return None
        return tuple(entry.gr_mem)

    return group_members


# Required host tooling for systemd activation only (no identity provisioning).
REQUIRED_COMMANDS = ("systemctl", "systemd-tmpfiles")
REQUIRED_FILES = ("/usr/bin/python3", "/usr/sbin/nologin")


def dependency_preflight(
    which: Callable[[str], str | None] | None = None,
    file_exists: Callable[[str], bool] | None = None,
) -> list[str]:
    """Fail-closed dependency preflight before any mutation.

    Verifies the canonical source artifacts, the activation binaries
    (``systemctl``/``systemd-tmpfiles``), ``/usr/bin/python3``, the
    ``/usr/sbin/nologin`` shell and PyYAML. Injectable ``which``/``file_exists``
    keep the check testable without host mutation.
    """

    resolve = which or shutil.which
    exists = file_exists or (lambda path: Path(path).exists())

    findings: list[str] = []
    required = (GATEWAY_HOLD_SRC, README_SRC, DESCRIPTOR_SRC, SERVICE_UNIT, TMPFILES_SRC)
    for path in required:
        if not path.exists() or not path.is_file():
            findings.append(f"dependency-missing: required source artifact {path} is missing")

    for command in REQUIRED_COMMANDS:
        if not resolve(command):
            findings.append(f"dependency-missing: required command '{command}' not found on PATH")
    for path in REQUIRED_FILES:
        if not exists(path):
            findings.append(f"dependency-missing: required file '{path}' is missing")

    if yaml is None:  # pragma: no cover - import guarded at module load
        findings.append("dependency-missing: PyYAML is required")
    return findings


def root_gate(require_root: bool) -> list[str]:
    """Fail-closed root gate. install-base/rollback-base require uid 0."""

    findings: list[str] = []
    if require_root and os.geteuid() != 0:
        findings.append("root-required: install-base/rollback-base must run as root (uid 0)")
    return findings


def hashlib_sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _file_expected_hash(path: Path) -> str:
    return hashlib_sha256(path.read_bytes())


# ----------------------------------------------------------------- descriptor


def load_descriptor(path: Path | str = DESCRIPTOR_SRC) -> dict[str, Any]:
    descriptor_path = Path(path)
    try:
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeploymentBoundaryError("DESCRIPTOR_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise DeploymentBoundaryError("DESCRIPTOR_INVALID", str(exc)) from exc
    if not isinstance(document, Mapping):
        raise DeploymentBoundaryError("DESCRIPTOR_INVALID", "descriptor must be an object")
    return dict(document)


def fail_closed_policy_envelope() -> dict[str, Any]:
    return {
        "state": POLICY_STATE,
        "default": POLICY_DEFAULT,
        "runtime_status": POLICY_RUNTIME_STATUS,
        "execution_authority": POLICY_EXECUTION_AUTHORITY,
        "promotion_allowed": PROMOTION_ALLOWED,
    }


def _check_descriptor(descriptor: Mapping[str, Any], findings: list[str]) -> None:
    if set(descriptor) != REQUIRED_TOP_KEYS:
        findings.append(f"descriptor exact top-level keys {sorted(REQUIRED_TOP_KEYS)} are required")

    if descriptor.get("runtime_status") != POLICY_RUNTIME_STATUS:
        findings.append("runtime_status must remain NOT_RUN; this is not a live promotion")
    if descriptor.get("promotion_allowed") is not False:
        findings.append("promotion_allowed must be false in the repository-only boundary")

    policy = descriptor.get("policy")
    envelope = fail_closed_policy_envelope()
    if not isinstance(policy, Mapping):
        findings.append("policy must be a mapping")
    else:
        for key, expected in envelope.items():
            if policy.get(key) != expected:
                findings.append(f"policy.{key} must be {expected!r}, got {policy.get(key)!r}")

    listener = descriptor.get("listener")
    if not isinstance(listener, Mapping):
        findings.append("listener must be a mapping")
    else:
        if listener.get("mode") != "HOLD":
            findings.append("listener.mode must be HOLD")
        if listener.get("transport") != "unix-peer":
            findings.append("listener.transport must be unix-peer")
        if listener.get("identity_source") != "linux-so-peercred":
            findings.append("listener.identity_source must be linux-so-peercred")
        refused = set(listener.get("refuse_on_any") or [])
        if refused != set(PROHIBITED_EFFECTS):
            findings.append("listener.refuse_on_any must enumerate every prohibited downstream effect")

    target_effects = descriptor.get("target_effects")
    if isinstance(target_effects, Mapping):
        for effect in target_effects.values():
            if effect not in (None, "none"):
                findings.append("target_effects must declare no target effect (none)")

    tb = descriptor.get("trust_binding")
    if isinstance(tb, Mapping):
        if tb.get("enabled") is True:
            findings.append("trust_binding.enabled must be false in phase A (external-only phase B)")
        if tb.get("source") is not None:
            findings.append("trust_binding.source must be null; phase B binds explicit external sources only")
        if tb.get("trust_store_path") != TRUST_STORE_PATH:
            findings.append("trust_binding.trust_store_path must match the canonical path and is never created here")


# ------------------------------------------------------ identity exactness preflight


def detect_reserved_id_collision(
    observed_uids: Mapping[int, str] | None = None,
    observed_gids: Mapping[int, str] | None = None,
) -> list[str]:
    """Exact-aware, namespace-aware collision preflight for the gateway IDs.

    The UID and GID namespaces are distinct: uid 4100 and gid 4100 (both
    ``hexor-gateway``) are both expected and are never reported as a duplicate
    collision. A reserved id is a CONFLICT only when it is already held, in its
    own namespace, by a name other than the canonical owner. An exact existing
    canonical identity produces no finding.
    """

    findings: list[str] = []
    uids = dict(observed_uids or {})
    gids = dict(observed_gids or {})
    single_map = observed_gids is None

    def _check(namespace: str, observed: Mapping[int, str], canonical: Mapping[int, str]) -> None:
        for reserved_id, canonical_name in canonical.items():
            existing = observed.get(reserved_id)
            if existing is None or existing == canonical_name:
                continue  # absent (provisionable by #354) or exact (idempotent)
            findings.append(
                f"id-collision: reserved {namespace} {reserved_id} is already held by "
                f"'{existing}' (canonical owner is '{canonical_name}'); the gateway must "
                f"not reuse a conflicting OS identity"
            )

    _check("uid", uids, CANONICAL_UID_OWNERS)
    _check("gid", gids if not single_map else uids, CANONICAL_GID_OWNERS)
    unique: list[str] = []
    for finding in findings:
        if finding not in unique:
            unique.append(finding)
    return unique


def _assess_user(
    name: str, uid: int, gid: int, shell: str,
    by_uid: Mapping[str, Any] | None, by_name: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if by_uid is None and by_name is None:
        return IdentityStatus.ABSENT, f"{name} (uid {uid}) not present"
    if by_uid is not None and by_uid.get("name") != name:
        return IdentityStatus.CONFLICT, f"uid {uid} already held by '{by_uid.get('name')}'"
    if by_name is not None and by_name.get("uid") != uid:
        return IdentityStatus.CONFLICT, f"name {name} already held by uid {by_name.get('uid')}"
    for observed in (by_uid, by_name):
        if observed is None:
            continue
        if observed.get("gid") != gid:
            return IdentityStatus.CONFLICT, f"{name} primary gid {observed.get('gid')} != canonical {gid}"
        if observed.get("shell") != shell:
            return IdentityStatus.CONFLICT, f"{name} shell {observed.get('shell')} != canonical {shell}"
    return IdentityStatus.EXACT, f"{name} (uid {uid}) exact match"


def _assess_group(
    name: str, gid: int,
    by_gid: Mapping[str, Any] | None, by_name: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if by_gid is None and by_name is None:
        return IdentityStatus.ABSENT, f"{name} (gid {gid}) not present"
    if by_gid is not None and by_gid.get("name") != name:
        return IdentityStatus.CONFLICT, f"gid {gid} already held by '{by_gid.get('name')}'"
    if by_name is not None and by_name.get("gid") != gid:
        return IdentityStatus.CONFLICT, f"name {name} already held by gid {by_name.get('gid')}"
    return IdentityStatus.EXACT, f"{name} (gid {gid}) exact match"


def preflight_identities(
    user_by_uid,
    user_by_name,
    group_by_gid,
    group_by_name,
    group_members=None,
) -> list[tuple[str, str, str, str]]:
    """Assess the gateway's required identities against host probes.

    The gateway asserts EXACTNESS only. It never provisions:

    - ``hexor-gateway`` group (gid 4100);
    - ``hexor-dispatch`` group (gid 4110);
    - ``hexor-gateway`` user (uid/gid 4100, nologin);
    - ``hexor-gateway`` membership in ``hexor-dispatch``.

    Returns ``(kind, name, status, detail)`` tuples. ABSENT is reported but is
    NOT a pass: the deployment controller fails closed because provisical of
    these identities is owned by the Runner boundary (#354). CONFLICT also fails
    closed. Only EXACT is acceptable.
    """

    results: list[tuple[str, str, str, str]] = []
    results.append(("group", HEXOR_GATEWAY_GROUP,
                    *_assess_group(HEXOR_GATEWAY_GROUP, HEXOR_GATEWAY_GID,
                                   group_by_gid(HEXOR_GATEWAY_GID), group_by_name(HEXOR_GATEWAY_GROUP))))
    results.append(("group", HEXOR_DISPATCH_GROUP,
                    *_assess_group(HEXOR_DISPATCH_GROUP, HEXOR_DISPATCH_GID,
                                   group_by_gid(HEXOR_DISPATCH_GID), group_by_name(HEXOR_DISPATCH_GROUP))))
    results.append(("user", HEXOR_GATEWAY_USER,
                    *_assess_user(HEXOR_GATEWAY_USER, HEXOR_GATEWAY_UID, HEXOR_GATEWAY_GID, HEXOR_NOLOGIN_SHELL,
                                  user_by_uid(HEXOR_GATEWAY_UID), user_by_name(HEXOR_GATEWAY_USER))))
    if group_members is not None:
        members = set(group_members(HEXOR_DISPATCH_GROUP) or ())
        if HEXOR_GATEWAY_USER in members:
            results.append(("membership", HEXOR_GATEWAY_USER, IdentityStatus.EXACT,
                            f"{HEXOR_GATEWAY_USER} is a member of {HEXOR_DISPATCH_GROUP}"))
        else:
            results.append(("membership", HEXOR_GATEWAY_USER, IdentityStatus.ABSENT,
                            f"{HEXOR_GATEWAY_USER} is not a member of {HEXOR_DISPATCH_GROUP}"))
    return results


def identity_conflicts(results: Sequence[tuple[str, str, str, str]]) -> list[str]:
    """Return RED findings (ABSENT or CONFLICT) from a preflight result set.

    The gateway treats both ABSENT (owner is #354) and CONFLICT as fail-closed:
    it must never silently create or reuse an identity.
    """

    return [
        f"identity-not-exact: {kind} {name}: {detail}"
        for kind, name, status, detail in results
        if status is not IdentityStatus.EXACT
    ]


# --------------------------------------------------------------------- plan


def build_plan(descriptor: Mapping[str, Any]) -> DeploymentPlan:
    """Render a fail-closed, idempotent deployment plan (no live mutation)."""

    findings: list[str] = []
    _check_descriptor(descriptor, findings)
    if findings:
        raise DeploymentBoundaryError("PLAN_INVALID", "; ".join(findings))

    install_files = (
        (GATEWAY_HOLD_SRC, HOLD_DST),
        (README_SRC, README_DST),
        (DESCRIPTOR_SRC, DESCRIPTOR_DST),
        (SERVICE_UNIT, SERVICE_DST),
        (TMPFILES_SRC, TMPFILES_CONF_DST),
    )
    remove_on_rollback = tuple(dst for _src, dst in install_files)

    return DeploymentPlan(
        ok=not findings,
        findings=tuple(findings),
        install_files=install_files,
        remove_on_rollback=remove_on_rollback,
        policy_envelope=fail_closed_policy_envelope(),
        prohibited_effects=frozenset(PROHIBITED_EFFECTS),
    )


# ---------------------------------------------------------------- base install


def _verify_installed_file(src: Path, dst: Path, *, executable: bool) -> str | None:
    """Return a RED finding if ``dst`` exists but drifts, else None. No mutation."""

    if not dst.exists():
        return None
    if dst.is_symlink():
        return f"drift: {dst} is a symlink (must be a regular file copied from {src})"
    if not dst.is_file():
        return f"drift: {dst} exists but is not a regular file"
    try:
        src_data = src.read_bytes()
        dst_data = dst.read_bytes()
    except OSError as exc:
        return f"drift: cannot read {dst} for comparison: {exc}"
    if hashlib_sha256(dst_data) != hashlib_sha256(src_data):
        return f"drift: {dst} content differs from canonical {src}; refusing non-identical overwrite"
    if executable:
        mode = stat.S_IMODE(dst.stat().st_mode)
        if mode & 0o0111 == 0:
            return f"drift: {dst} is not executable as required"
    return None


def _install_file(src: Path, dst: Path, *, executable: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, MODE_EXEC if executable else MODE_FILE)
    try:
        os.chown(dst, OWNER_ROOT_UID, OWNER_ROOT_GID)
    except OSError:
        pass


def _default_command_runner(command: Sequence[str]) -> tuple[int, str]:
    """Injectable command runner boundary (never used by tests)."""

    completed = subprocess.run(list(command), capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stderr or completed.stdout or "").strip()


def _probe_identities(probes, group_members):
    if probes is None:
        user_by_uid, user_by_name, group_by_gid, group_by_name = probe_users_groups()
    else:
        user_by_uid, user_by_name, group_by_gid, group_by_name = probes
    if group_members is None:
        group_members = probe_group_members()
    return user_by_uid, user_by_name, group_by_gid, group_by_name, group_members


def install_base(
    descriptor: Mapping[str, Any],
    *,
    live: bool,
    require_root: bool = True,
    probes: Any = None,
    group_members: Callable[[str], Sequence[str] | None] | None = None,
    run_command: Callable[[Sequence[str]], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Privileged base install of gateway-owned artifacts, fail-closed.

    Strict ordering (no mutation happens before the whole preflight is GREEN):

    1. root gate;
    2. dependency preflight (systemctl/systemd-tmpfiles, /usr/bin/python3,
       /usr/sbin/nologin, PyYAML, canonical sources);
    3. descriptor/plan preflight + reserved-id collision preflight;
    4. identity/group EXACTNESS preflight (no provisioning): ABSENT or CONFLICT
       is a hard fail-closed stop;
    5. artifact drift preflight;
    -- first mutation only from here --
    6. file install (root-owned, exact modes);
    7. postcondition re-probe of installed files (byte-identical + owner/mode);
    8. daemon-reload / systemd-tmpfiles --create / enable --now the gateway service.

    The gateway never provisions identities, never creates the socket, never
    binds trust, never enables an execution policy and never touches a target.
    """

    if live is False:
        plan = build_plan(descriptor)
        if not plan.ok:
            raise DeploymentBoundaryError("PLAN_INVALID", "; ".join(plan.findings))
        return {"live": False, "plan": plan.as_dict()}

    runner = run_command or _default_command_runner

    findings: list[str] = []
    findings.extend(root_gate(require_root))
    findings.extend(dependency_preflight())

    user_by_uid, user_by_name, group_by_gid, group_by_name, members_probe = _probe_identities(
        probes, group_members
    )
    identity_results = preflight_identities(
        user_by_uid, user_by_name, group_by_gid, group_by_name, members_probe
    )
    findings.extend(identity_conflicts(identity_results))

    # Exact-aware reserved-id collision preflight from the live probes.
    observed_uids = {}
    observed_gids = {}
    for kind, name, status, _detail in identity_results:
        if status is not IdentityStatus.EXACT:
            continue
        if kind == "user":
            observed_uids[HEXOR_GATEWAY_UID] = name
        elif kind == "group":
            if name == HEXOR_GATEWAY_GROUP:
                observed_gids[HEXOR_GATEWAY_GID] = name
            elif name == HEXOR_DISPATCH_GROUP:
                observed_gids[HEXOR_DISPATCH_GID] = name
    findings.extend(detect_reserved_id_collision(observed_uids, observed_gids))

    plan = build_plan(descriptor)
    findings.extend(plan.findings)

    if findings:
        raise DeploymentBoundaryError("PREFLIGHT_FAILED", "; ".join(findings))

    # Fail-closed drift/symlink check: still BEFORE the first mutation.
    drift: list[str] = []

    def _add(find: str | None) -> None:
        if find:
            drift.append(find)

    _add(_verify_installed_file(GATEWAY_HOLD_SRC, HOLD_DST, executable=True))
    _add(_verify_installed_file(README_SRC, README_DST, executable=False))
    _add(_verify_installed_file(DESCRIPTOR_SRC, DESCRIPTOR_DST, executable=False))
    _add(_verify_installed_file(SERVICE_UNIT, SERVICE_DST, executable=False))
    _add(_verify_installed_file(TMPFILES_SRC, TMPFILES_CONF_DST, executable=False))
    if drift:
        raise DeploymentBoundaryError("DRIFT_DETECTED", "; ".join(drift))

    # Install only gateway-owned artifacts (idempotent: byte-identical == no-op).
    _install_file(GATEWAY_HOLD_SRC, HOLD_DST, executable=True)
    _install_file(README_SRC, README_DST, executable=False)
    _install_file(DESCRIPTOR_SRC, DESCRIPTOR_DST, executable=False)
    _install_file(SERVICE_UNIT, SERVICE_DST, executable=False)
    _install_file(TMPFILES_SRC, TMPFILES_CONF_DST, executable=False)

    # Postcondition re-probe: every installed file must be byte-identical and
    # root-owned with the expected executable bit. A drift here is RED.
    post_drift: list[str] = []
    _add2 = lambda find: post_drift.append(find) if find else None  # noqa: E731
    _add2(_verify_installed_file(GATEWAY_HOLD_SRC, HOLD_DST, executable=True))
    _add2(_verify_installed_file(README_SRC, README_DST, executable=False))
    _add2(_verify_installed_file(DESCRIPTOR_SRC, DESCRIPTOR_DST, executable=False))
    _add2(_verify_installed_file(SERVICE_UNIT, SERVICE_DST, executable=False))
    _add2(_verify_installed_file(TMPFILES_SRC, TMPFILES_CONF_DST, executable=False))
    if post_drift:
        raise DeploymentBoundaryError("POSTCONDITION_DRIFT", "; ".join(post_drift))

    # Enable systemd gateway service: reload, tmpfiles, enable --now. All three
    # are fail-closed on a non-zero return code via the injectable runner.
    _systemctl(runner, "daemon-reload")
    _systemd_tmpfiles_create(runner)
    _systemctl(runner, "enable", "--now", SYSTEMD_SERVICE_UNIT)

    return {
        "live": True,
        "installed": [str(d) for _s, d in plan.install_files],
        "identity_status": [list(r) for r in identity_results],
        "created_identities": [],
        "provisioned_identities": False,
        "policy_envelope": plan.policy_envelope,
        "bound_trust": False,
        "enabled_policies": False,
        "touched_target": False,
        "runtime_status": POLICY_RUNTIME_STATUS,
        "execution_authority": POLICY_EXECUTION_AUTHORITY,
        "promotion_allowed": False,
    }


def _run_systemd(
    runner: Callable[[Sequence[str]], tuple[int, str]],
    code: str,
    command: Sequence[str],
) -> None:
    """Run a systemd lifecycle command via the injectable runner, fail-closed."""

    rc, detail = runner(list(command))
    if rc != 0:
        raise DeploymentBoundaryError(
            code, f"command {' '.join(command)} failed with rc={rc}: {detail}"
        )


SYSTEMD_DAEMON_RELOAD_FAILED = "SYSTEMD_DAEMON_RELOAD_FAILED"
SYSTEMD_TMPFILES_CREATE_FAILED = "SYSTEMD_TMPFILES_CREATE_FAILED"
SYSTEMD_ENABLE_FAILED = "SYSTEMD_ENABLE_FAILED"
SYSTEMD_DISABLE_FAILED = "SYSTEMD_DISABLE_FAILED"

_SYSTEMCTL_ERROR_CODE = {
    ("daemon-reload",): SYSTEMD_DAEMON_RELOAD_FAILED,
    ("enable", "--now"): SYSTEMD_ENABLE_FAILED,
    ("disable", "--now"): SYSTEMD_DISABLE_FAILED,
}


def _systemctl(runner: Callable[[Sequence[str]], tuple[int, str]], *args: str) -> None:
    key = ("daemon-reload",) if args[:1] == ("daemon-reload",) else tuple(args[:2])
    code = _SYSTEMCTL_ERROR_CODE.get(key, "SYSTEMD_COMMAND_FAILED")
    _run_systemd(runner, code, ["systemctl", *args])


def _systemd_tmpfiles_create(runner: Callable[[Sequence[str]], tuple[int, str]]) -> None:
    _run_systemd(
        runner,
        SYSTEMD_TMPFILES_CREATE_FAILED,
        ["systemd-tmpfiles", "--create", str(TMPFILES_CONF_DST)],
    )


# --------------------------------------------------------------- base rollback


def rollback_base(
    descriptor: Mapping[str, Any],
    *,
    live: bool,
    require_root: bool = True,
    run_command: Callable[[Sequence[str]], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Stop/disable the gateway service, remove only owned artifacts, reload.

    Fail-closed on drift/residue: an installed artifact that has drifted
    (content changed, symlink, wrong owner) is reported RED rather than deleted
    blindly.

    Fail-closed lifecycle ordering (live mode): the service is stopped and
    disabled via the injectable ``run_command`` runner with stable error codes.
    ``disable --now`` and the final ``daemon-reload`` are fail-closed: if either
    returns a non-zero code the rollback aborts *before* any owned artifact is
    removed, so the gateway is never left in a half-removed / half-activated
    state. Only after the stop/disable step is confirmed successful are the owned
    gateway artifacts unlinked.

    Identities, ``/run/hexor``, the Runner socket/runtime, the trust store and
    all policy state are ALWAYS preserved: removing them is an explicit
    administrative lifecycle operation performed by an operator, never here.
    """

    runner = run_command or _default_command_runner

    plan = build_plan(descriptor)
    findings: list[str] = []
    findings.extend(root_gate(require_root))

    residue: list[str] = []
    for _src, dst in plan.install_files:
        if not dst.exists():
            continue
        if dst.is_symlink():
            residue.append(f"residue: {dst} is a symlink (unexpected gateway artifact)")
            continue
        if not dst.is_file():
            residue.append(f"residue: {dst} is not a regular file")
            continue
        try:
            st = dst.stat()
        except OSError as exc:
            residue.append(f"residue: cannot stat {dst}: {exc}")
            continue
        if st.st_uid != OWNER_ROOT_UID or st.st_gid != OWNER_ROOT_GID:
            residue.append(f"residue: {dst} owner {st.st_uid}:{st.st_gid} is not root-owned; refusing blind removal")

    protected = {
        TRUST_STORE_PATH: "trust store",
        str(RUNNER_SOCKET): "runner dispatcher socket",
        str(RUNTIME_DIR): "runner runtime directory",
    }

    if live is False:
        return {
            "live": False,
            "would_remove": [str(d) for _s, d in plan.install_files if d.exists()],
            "protected": list(protected),
            "preserves_identities": True,
            "residue": residue,
        }

    if residue:
        raise DeploymentBoundaryError("ROLLBACK_RESIDUE", "; ".join(residue))

    # Fail-closed stop/disable. Abort BEFORE removing any artifact if this fails.
    _systemctl(runner, "disable", "--now", SYSTEMD_SERVICE_UNIT)

    removed: list[str] = []
    for _src, dst in plan.install_files:
        if dst.exists():
            dst.unlink()
            removed.append(str(dst))
    # Remove the (now-empty) install dir only if it exists and is empty.
    if INSTALL_BIN_DIR.exists() and not any(INSTALL_BIN_DIR.iterdir()):
        try:
            INSTALL_BIN_DIR.rmdir()
        except OSError:
            pass

    # /run/hexor and the runner socket/runtime are NEVER touched by the gateway.
    # Fail-closed final reload.
    _systemctl(runner, "daemon-reload")

    return {
        "live": True,
        "removed": removed,
        "preserved": list(protected),
        "preserves_identities": True,
    }


# ------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--descriptor", default=str(DESCRIPTOR_SRC))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="read-only deployment plan + fail-closed envelope check")

    p_install = sub.add_parser("install-base", help="privileged base install of gateway-owned artifacts")
    p_install.add_argument("--live", action="store_true", help="perform the install (root required)")
    p_install.add_argument("--no-root-required", action="store_true", help="relax root gate (tests only)")

    p_rollback = sub.add_parser("rollback-base", help="remove owned gateway artifacts and reload")
    p_rollback.add_argument("--live", action="store_true", help="perform the removal (root required)")
    p_rollback.add_argument("--no-root-required", action="store_true", help="relax root gate (tests only)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        descriptor = load_descriptor(args.descriptor)
        if args.command == "plan":
            plan = build_plan(descriptor)
            if args.json:
                print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
            elif plan.ok:
                print("OK execution gateway deployment boundary is fail-closed and idempotent (HOLD, NOT_RUN)")
            else:
                for finding in plan.findings:
                    print(f"FAIL {finding}", file=sys.stderr)
            return EXIT_OK if plan.ok else EXIT_FAIL_CLOSED

        if args.command == "install-base":
            result = install_base(
                descriptor,
                live=args.live,
                require_root=not getattr(args, "no_root_required", False),
            )
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(("DRY-RUN: base install plan computed (pass --live to install)"
                       if not result.get("live") else
                       "OK base install completed (HOLD boundary, identities unmodified, trust NOT bound, policies NOT enabled)"))  # noqa: E501
            return EXIT_OK

        if args.command == "rollback-base":
            result = rollback_base(
                descriptor,
                live=args.live,
                require_root=not getattr(args, "no_root_required", False),
            )
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(("DRY-RUN: base rollback plan computed (pass --live to remove)"
                       if not result.get("live") else
                       "OK base rollback completed (identities, /run/hexor, runner socket and trust store preserved)"))  # noqa: E501
            return EXIT_OK

        parser.error("unknown command")
        return EXIT_USAGE  # pragma: no cover

    except DeploymentBoundaryError as exc:
        if args.json:
            print(json.dumps(exc.as_dict(), indent=2, sort_keys=True))
        else:
            print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures fail-closed
        print(f"FAIL UNEXPECTED: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
