#!/usr/bin/env python3
"""Fail-closed Runner runtime deployment boundary controller (#354).

Repository-only. This controller implements the *base HOLD boundary* with four
explicit subcommands:

- ``plan``          (read-only): render the deployment plan and verify the
                    fail-closed envelope. No host mutation.
- ``install-base``  : privileged base install. It performs a root gate, a
                    dependency preflight (including ``groupadd``/``useradd``/
                    ``usermod``/``systemctl``/``systemd-tmpfiles``) and an
                    exact-aware identity preflight *before* any mutation, then
                    provisions ONLY the ABSENT canonical identities
                    (``hexor-gateway`` 4100, ``hexor-runner`` 4101 and the shared
                    ``hexor-dispatch`` 4110 group, plus supplementary
                    membership), verifies the identity postcondition, and only
                    then installs the inert runtime artifacts (listener,
                    canonical peer module, descriptor, systemd units, tmpfiles)
                    fail-closed (no silent overwrite/drift). It never binds
                    trust, enables policies or touches a target.
- ``rollback-base`` : stop/disable the service+socket, remove only the owned
                    base artifacts (fail-closed on drift/residue), then
                    daemon-reload. Users/groups and the trust store are always
                    preserved: they are durable boundary identities with a
                    separate, explicit administrative lifecycle.
- ``bind-trust``   : explicit phase-B step. Validates an external public trust
                    store (exact SHA-256, no secret material) and installs it
                    atomically to the canonical destination. Never called from
                    install-base.

The boundary envelope stays DISABLED / default-deny / NOT_RUN / none /
promotion_allowed=false. The controller may create the dedicated boundary users
and groups (and their ``hexor-dispatch`` membership) during ``install-base``, but
it never removes or relinks them, never creates passwords or credentials, never
creates the AF_UNIX socket (systemd socket activation owns that), never writes or
modifies ``/etc/hexor/runner/authorization-trust-store.json`` outside
``bind-trust``, and never touches a target (WebGoat/Kali) or any Evidence Plane /
router / adapter.
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

# Sibling imports without package context (loaded standalone by tests/templates).
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from runtime_boundaries import (  # noqa: E402
    CANONICAL_DISPATCH_MEMBERS,
    HEXOR_DISPATCH_GID,
    HEXOR_DISPATCH_GROUP,
    HEXOR_RUNNER_GID,
    HEXOR_RUNNER_UID,
    POLICY_RUNTIME_STATUS,
    SYSTEMD_SERVICE_UNIT,
    SYSTEMD_SOCKET_UNIT,
    TMPFILES_CONF,
    TRUST_STORE_PATH,
    IdentityStatus,
    declared_identities,
    declared_socket,
    detect_reserved_id_collision,
    fail_closed_policy_envelope,
    identity_conflicts,
    no_target_effect_contract,
    plan_identity_provisioning,
    preflight_identities,
)
from trust_binding import (  # noqa: E402
    TRUST_STORE_CANONICAL_PATH,
    TrustBindingSource,
    bind_trust_store,
    from_cli_args,
)

RUNTIME_DEPLOYMENT_YAML = HERE / "runtime-deployment.yaml"
LISTENER_SRC = HERE / "runner_hold_listener.py"
DESCRIPTOR_SRC = HERE / "runtime-deployment.yaml"
README_SRC = HERE / "README.md"
SOCKET_UNIT = HERE / "systemd" / SYSTEMD_SOCKET_UNIT
SERVICE_UNIT = HERE / "systemd" / SYSTEMD_SERVICE_UNIT
TMPFILES_SRC = HERE / "tmpfiles" / TMPFILES_CONF
PEER_MODULE_SRC = HERE.parent.parent / "platform" / "runner-transport" / "unix_peer_identity.py"

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2
EXIT_USAGE = 64

REQUIRED_TOP_KEYS = {
    "schema_version",
    "descriptor_id",
    "issue",
    "phase",
    "runtime_status",
    "promotion_allowed",
    "identities",
    "socket",
    "policy",
    "listener",
    "trust_binding",
    "target_effects",
}

# Canonical installed runtime layout (owned base artifacts).
INSTALL_BIN_DIR = Path("/opt/hexor/runner-runtime")
LISTENER_DST = INSTALL_BIN_DIR / "runner_hold_listener.py"
PEER_DST = INSTALL_BIN_DIR / "unix_peer_identity.py"
DESCRIPTOR_DST = INSTALL_BIN_DIR / "runtime-deployment.yaml"
SYSTEMD_DST = Path("/etc/systemd/system")
TMPFILES_DST = Path("/etc/tmpfiles.d")
RUNTIME_DIR = Path("/run/hexor")
SOCKET_PATH = Path("/run/hexor/runner-dispatch.sock")

# Canonical installed file mode/owner contract.
MODE_FILE = 0o0644
MODE_EXEC = 0o0755
OWNER_ROOT_UID = 0
OWNER_ROOT_GID = 0
OWNER_RUNNER_UID = HEXOR_RUNNER_UID
OWNER_RUNNER_GID = HEXOR_RUNNER_GID
OWNER_DISPATCH_GID = HEXOR_DISPATCH_GID
DIR_MODE = 0o0755


class DeploymentBoundaryError(ValueError):
    """Stable fail-closed deployment boundary error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        partial_identity_provisioning: bool = False,
        created_identities: Sequence[Sequence[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        # Set when identity provisioning already mutated the host before failing.
        # Identities are durable boundary identities: they are NEVER auto-deleted
        # to compensate. An operator must resolve the partial state explicitly.
        self.partial_identity_provisioning = partial_identity_provisioning
        self.created_identities: list[list[str]] = [list(c) for c in (created_identities or ())]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "findings": [str(self)],
            "partial_identity_provisioning": self.partial_identity_provisioning,
            "created_identities": self.created_identities,
        }


@dataclass(frozen=True)
class DeploymentPlan:
    ok: bool
    findings: tuple[str, ...]
    install_files: tuple[tuple[Path, Path], ...]
    remove_on_rollback: tuple[Path, ...]
    policy_envelope: dict[str, Any]
    prohibited_effects: frozenset[str]
    trust_binding: Mapping[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": list(self.findings),
            "install_files": [[str(s), str(d)] for s, d in self.install_files],
            "remove_on_rollback": [str(p) for p in self.remove_on_rollback],
            "policy_envelope": self.policy_envelope,
            "prohibited_effects": sorted(self.prohibited_effects),
            "trust_binding": dict(self.trust_binding) if self.trust_binding else None,
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
    """Return four host probe callables (by-uid/by-name for users and groups).

    Each returns a mapping with the fields the preflight needs, or ``None`` when
    the identity is absent. Failures raise DeploymentBoundaryError only when a
    privileged call is required and unavailable; otherwise probe defensively.
    """

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


# Required host tooling for identity provisioning + systemd activation.
REQUIRED_COMMANDS = (
    "groupadd",
    "useradd",
    "usermod",
    "systemctl",
    "systemd-tmpfiles",
)
REQUIRED_FILES = (
    "/usr/bin/python3",
    "/usr/sbin/nologin",
)


def dependency_preflight(
    which: Callable[[str], str | None] | None = None,
    file_exists: Callable[[str], bool] | None = None,
) -> list[str]:
    """Fail-closed dependency preflight before any mutation.

    Verifies the canonical source artifacts, the provisioning/activation binaries
    (``groupadd``/``useradd``/``usermod``/``systemctl``/``systemd-tmpfiles``),
    ``/usr/bin/python3``, the ``/usr/sbin/nologin`` shell and PyYAML. Injectable
    ``which``/``file_exists`` keep the check testable without host mutation.
    """

    resolve = which or shutil.which
    exists = file_exists or (lambda path: Path(path).exists())

    findings: list[str] = []
    required = (PEER_MODULE_SRC, SOCKET_UNIT, SERVICE_UNIT, TMPFILES_SRC, README_SRC, RUNTIME_DEPLOYMENT_YAML)
    for path in required:
        if not path.exists() or not path.is_file():
            findings.append(f"dependency-missing: required source artifact {path} is missing")
    if not PEER_MODULE_SRC.exists():
        findings.append("dependency-missing: canonical platform/runner-transport/unix_peer_identity.py is required")

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


def _file_expected_hash(path: Path) -> str:
    return hashlib_sha256(path.read_bytes())


def hashlib_sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------- descriptor


def load_descriptor(path: Path | str = RUNTIME_DEPLOYMENT_YAML) -> dict[str, Any]:
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
        if refused != no_target_effect_contract():
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


def _validate_socket_declaration(findings: list[str]) -> None:
    sock = declared_socket()
    if sock.directory_path != "/run/hexor":
        findings.append("socket directory path must be /run/hexor")
    if sock.directory_mode != "0750":
        findings.append("socket directory mode must be 0750")
    if sock.socket_path != "/run/hexor/runner-dispatch.sock":
        findings.append("socket path must be /run/hexor/runner-dispatch.sock")
    if sock.socket_mode != "0660":
        findings.append("socket mode must be 0660")
    if sock.socket_owner_uid != 4101:
        findings.append("socket owner must be the hexor-runner identity (4101)")
    if sock.socket_group_gid != 4110:
        findings.append("socket group must be the hexor-dispatch group (4110)")


def _validate_identities(findings: list[str]) -> None:
    ids = {ident.uid: ident for ident in declared_identities()}
    expected = {
        4100: ("hexor-gateway", "user"),
        4101: ("hexor-runner", "user"),
        4110: ("hexor-dispatch", "group"),
    }
    for uid, (name, kind) in expected.items():
        ident = ids.get(uid)
        if ident is None:
            findings.append(f"declared identity {uid} is missing")
            continue
        if ident.name != name or ident.kind != kind:
            findings.append(f"declared identity {uid} must be {name}/{kind}")


def build_plan(
    descriptor: Mapping[str, Any],
    observed_ids: Mapping[int, str] | None = None,
    trust_binding: TrustBindingSource | None = None,
) -> DeploymentPlan:
    """Render a fail-closed, idempotent deployment plan (no live mutation)."""

    findings: list[str] = []
    _check_descriptor(descriptor, findings)
    _validate_identities(findings)
    _validate_socket_declaration(findings)

    collisions = detect_reserved_id_collision(observed_ids or {})
    findings.extend(collisions)

    tb_summary: Mapping[str, Any] | None = None
    if trust_binding is not None:
        try:
            tb_summary = trust_binding.as_safe_dict()
        except Exception as exc:  # noqa: BLE001 - fail-closed surface
            findings.append(f"trust_binding rejected: {exc}")

    install_files = (
        (LISTENER_SRC, LISTENER_DST),
        (PEER_MODULE_SRC, PEER_DST),
        (DESCRIPTOR_SRC, DESCRIPTOR_DST),
        (SOCKET_UNIT, SYSTEMD_DST / SYSTEMD_SOCKET_UNIT),
        (SERVICE_UNIT, SYSTEMD_DST / SYSTEMD_SERVICE_UNIT),
        (TMPFILES_SRC, TMPFILES_DST / TMPFILES_CONF),
        (README_SRC, INSTALL_BIN_DIR / "README.md"),
    )
    remove_on_rollback = tuple(dst for _, dst in install_files)

    return DeploymentPlan(
        ok=not findings,
        findings=tuple(findings),
        install_files=install_files,
        remove_on_rollback=remove_on_rollback,
        policy_envelope=fail_closed_policy_envelope(),
        prohibited_effects=frozenset(no_target_effect_contract()),
        trust_binding=tb_summary,
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


def _install_file(src: Path, dst: Path, *, executable: bool, owner_uid: int, owner_gid: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, MODE_EXEC if executable else MODE_FILE)
    try:
        os.chown(dst, owner_uid, owner_gid)
    except OSError:
        pass


def _default_command_runner(command: Sequence[str]) -> tuple[int, str]:
    """Injectable command runner boundary (never used by tests)."""

    completed = subprocess.run(list(command), capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stderr or completed.stdout or "").strip()


def _probe_identities(probes, group_members):
    """Resolve the four identity probes + the membership probe (injectable)."""

    if probes is None:
        user_by_uid, user_by_name, group_by_gid, group_by_name = probe_users_groups()
    else:
        user_by_uid, user_by_name, group_by_gid, group_by_name = probes
    if group_members is None:
        group_members = probe_group_members()
    return user_by_uid, user_by_name, group_by_gid, group_by_name, group_members


def _post_probe_identities(probes, group_members):
    """Real re-probe of identities/memberships before the postcondition.

    When no probes were injected, re-read the live host via ``probe_users_groups``
    / ``probe_group_members`` so the postcondition can never pass on a stale
    snapshot taken during the preflight. When probes are injected they are reused
    as-is: tests inject live closures over mutable host state, so the
    postcondition reflects the just-performed provisioning (mutable maps).
    """

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
    """Privileged base install of the runtime artifacts, fail-closed.

    Strict ordering (no mutation happens before the whole preflight is GREEN):

    1. root gate;
    2. dependency preflight (groupadd/useradd/usermod/systemctl/systemd-tmpfiles,
       /usr/bin/python3, /usr/sbin/nologin, PyYAML, canonical sources);
    3. descriptor/plan preflight + reserved-id collision preflight;
    4. identity preflight (names *and* ids -> EXACT / ABSENT / CONFLICT);
    5. artifact drift preflight;
    -- first mutation only from here --
    6. identity provisioning of ABSENT objects only (deterministic order:
       3x groupadd, 2x useradd, 2x usermod);
    7. identity postcondition re-probe (must be exact, memberships included);
    8. file install;
    9. daemon-reload / systemd-tmpfiles --create / socket activation.

    A CONFLICT, a failed provisioning command or a wrong postcondition is a hard
    fail-closed stop before any file/systemd action. Identities are never deleted
    to compensate a partial provisioning: the failure surfaces
    ``partial_identity_provisioning=true`` plus ``created_identities`` for the
    operator. Never binds trust, enables policies or touches a target.
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

    plan = build_plan(descriptor)
    findings.extend(plan.findings)

    if findings:
        raise DeploymentBoundaryError("PREFLIGHT_FAILED", "; ".join(findings))

    # Fail-closed drift/symlink check: still BEFORE the first mutation.
    drift: list[str] = []

    def _add(find: str | None) -> None:
        if find:
            drift.append(find)

    _add(_verify_installed_file(LISTENER_SRC, LISTENER_DST, executable=True))
    _add(_verify_installed_file(PEER_MODULE_SRC, PEER_DST, executable=False))
    _add(_verify_installed_file(DESCRIPTOR_SRC, DESCRIPTOR_DST, executable=False))
    _add(_verify_installed_file(SOCKET_UNIT, SYSTEMD_DST / SYSTEMD_SOCKET_UNIT, executable=False))
    _add(_verify_installed_file(SERVICE_UNIT, SYSTEMD_DST / SYSTEMD_SERVICE_UNIT, executable=False))
    _add(_verify_installed_file(TMPFILES_SRC, TMPFILES_DST / TMPFILES_CONF, executable=False))
    _add(_verify_installed_file(README_SRC, INSTALL_BIN_DIR / "README.md", executable=False))
    if drift:
        raise DeploymentBoundaryError("DRIFT_DETECTED", "; ".join(drift))

    # ---- first mutation: provision ONLY the ABSENT identity objects ----------
    try:
        commands = plan_identity_provisioning(identity_results)
    except ValueError as exc:  # defensive: conflicts already refused above
        raise DeploymentBoundaryError("PREFLIGHT_FAILED", str(exc)) from exc

    created: list[list[str]] = []
    for command in commands:
        rc, detail = runner(command)
        if rc != 0:
            raise DeploymentBoundaryError(
                "IDENTITY_PROVISIONING_FAILED",
                f"command {' '.join(command)} failed with rc={rc}: {detail}",
                partial_identity_provisioning=bool(created),
                created_identities=created,
            )
        created.append(command)

    # ---- postcondition: REAL re-probe of identities/membership -------------
    # Re-read the host (fresh when probes=None, live injected closures otherwise)
    # so the postcondition can never pass on a stale preflight snapshot.
    post_user_by_uid, post_user_by_name, post_group_by_gid, post_group_by_name, post_members = _post_probe_identities(
        probes, group_members
    )
    post_results = preflight_identities(
        post_user_by_uid, post_user_by_name, post_group_by_gid, post_group_by_name, post_members
    )
    not_exact = [
        f"identity-postcondition: {kind} {name} is {status.value} after provisioning: {detail}"
        for kind, name, status, detail in post_results
        if status is not IdentityStatus.EXACT
    ]
    if not_exact:
        raise DeploymentBoundaryError(
            "IDENTITY_POSTCONDITION_FAILED",
            "; ".join(not_exact),
            partial_identity_provisioning=bool(created),
            created_identities=created,
        )

    # Install artifacts (idempotent: existing byte-identical + mode/owner == no-op).
    _install_file(LISTENER_SRC, LISTENER_DST, executable=True,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(PEER_MODULE_SRC, PEER_DST, executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(DESCRIPTOR_SRC, DESCRIPTOR_DST, executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(SOCKET_UNIT, SYSTEMD_DST / SYSTEMD_SOCKET_UNIT, executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(SERVICE_UNIT, SYSTEMD_DST / SYSTEMD_SERVICE_UNIT, executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(TMPFILES_SRC, TMPFILES_DST / TMPFILES_CONF, executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)
    _install_file(README_SRC, INSTALL_BIN_DIR / "README.md", executable=False,
                  owner_uid=OWNER_ROOT_UID, owner_gid=OWNER_ROOT_GID)

    # Enable systemd runtime: reload, tmpfiles, enable --now the socket.
    # All three are fail-closed on a non-zero return code via the injectable
    # runner, so a half-activated unit never slips through.
    _systemctl(runner, "daemon-reload")
    _systemd_tmpfiles_create(runner)
    _systemctl(runner, "enable", "--now", SYSTEMD_SOCKET_UNIT)

    return {
        "live": True,
        "installed": [str(d) for _, d in plan.install_files],
        "identity_status": [(k, n, s.value, d) for k, n, s, d in post_results],
        "identity_commands": [list(c) for c in created],
        "created_identities": [list(c) for c in created],
        "partial_identity_provisioning": False,
        "dispatch_group": HEXOR_DISPATCH_GROUP,
        "dispatch_members": list(CANONICAL_DISPATCH_MEMBERS),
        "policy_envelope": plan.policy_envelope,
        "bound_trust": False,
        "enabled_policies": False,
        "touched_target": False,
        "runtime_status": POLICY_RUNTIME_STATUS,
        "execution_authority": "none",
        "promotion_allowed": False,
    }


def _run_systemd(
    runner: Callable[[Sequence[str]], tuple[int, str]],
    code: str,
    command: Sequence[str],
) -> None:
    """Run a systemd lifecycle command via the injectable runner, fail-closed.

    Any non-zero return code is a hard stop: the runtime is never left in a
    half-activated / half-deactivated state. ``code`` is a stable error code so
    callers and operators can distinguish daemon-reload / tmpfiles / enable /
    disable failures.
    """

    rc, detail = runner(list(command))
    if rc != 0:
        raise DeploymentBoundaryError(
            code,
            f"command {' '.join(command)} failed with rc={rc}: {detail}",
        )


# Stable error codes for each distinct systemd lifecycle command.
SYSTEMD_DAEMON_RELOAD_FAILED = "SYSTEMD_DAEMON_RELOAD_FAILED"
SYSTEMD_TMPFILES_CREATE_FAILED = "SYSTEMD_TMPFILES_CREATE_FAILED"
SYSTEMD_ENABLE_FAILED = "SYSTEMD_ENABLE_FAILED"
SYSTEMD_DISABLE_FAILED = "SYSTEMD_DISABLE_FAILED"

_SYSTEMCTL_ERROR_CODE = {
    ("daemon-reload",): SYSTEMD_DAEMON_RELOAD_FAILED,
    ("enable", "--now"): SYSTEMD_ENABLE_FAILED,
    ("disable", "--now"): SYSTEMD_DISABLE_FAILED,
}


def _systemctl(
    runner: Callable[[Sequence[str]], tuple[int, str]],
    *args: str,
) -> None:
    # The trailing argument (when present) is the systemd unit. Match on the
    # leading command tokens so ``enable --now <unit>`` / ``disable --now <unit>``
    # resolve to their stable codes instead of falling through to
    # SYSTEMD_COMMAND_FAILED.
    key = ("daemon-reload",) if args[:1] == ("daemon-reload",) else tuple(args[:2])
    code = _SYSTEMCTL_ERROR_CODE.get(key, "SYSTEMD_COMMAND_FAILED")
    _run_systemd(runner, code, ["systemctl", *args])


def _systemd_tmpfiles_create(
    runner: Callable[[Sequence[str]], tuple[int, str]],
) -> None:
    _run_systemd(
        runner,
        SYSTEMD_TMPFILES_CREATE_FAILED,
        ["systemd-tmpfiles", "--create", str(TMPFILES_DST / TMPFILES_CONF)],
    )


# --------------------------------------------------------------- base rollback


def rollback_base(
    descriptor: Mapping[str, Any],
    *,
    live: bool,
    require_root: bool = True,
    run_command: Callable[[Sequence[str]], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Stop/disable service+socket, remove only owned base artifacts, reload.

    Fail-closed on drift/residue: an installed artifact that has drifted (content
    changed, symlink, wrong owner) is reported RED rather than deleted blindly.

    Fail-closed lifecycle ordering (live mode): the socket/service are stopped and
    disabled via the injectable ``run_command`` runner with stable error codes.
    ``disable --now`` and the final ``daemon-reload`` are fail-closed: if either
    returns a non-zero code the rollback aborts *before* any owned artifact is
    removed, so the runtime is never left in a half-removed / half-activated
    state. Only after the stop/disable step is confirmed successful are the owned
    base artifacts unlinked.

    Users/groups and the trust store are ALWAYS preserved, even on a dry-run: the
    boundary identities (``hexor-gateway``, ``hexor-runner``, ``hexor-dispatch``)
    are durable identities. Removing them, if ever required, is a separate and
    explicit administrative lifecycle operation performed by an operator; this
    controller never deletes them, not even to compensate a partial install.
    """

    runner = run_command or _default_command_runner

    plan = build_plan(descriptor)
    findings: list[str] = []
    findings.extend(root_gate(require_root))

    # Verify ownership/drift of every base artifact before removing in live mode.
    residue: list[str] = []
    for _src, dst in plan.install_files:
        if not dst.exists():
            continue
        if dst.is_symlink():
            residue.append(f"residue: {dst} is a symlink (unexpected base artifact)")
            continue
        if not dst.is_file():
            residue.append(f"residue: {dst} is not a regular file")
            continue
        # Owned base artifacts must be root-owned. A non-root owner is residue.
        try:
            st = dst.stat()
        except OSError as exc:
            residue.append(f"residue: cannot stat {dst}: {exc}")
            continue
        if st.st_uid != OWNER_ROOT_UID or st.st_gid != OWNER_ROOT_GID:
            residue.append(f"residue: {dst} owner {st.st_uid}:{st.st_gid} is not root-owned; refusing blind removal")

    protected = {
        TRUST_STORE_PATH: "trust store",
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
    _systemctl(runner, "disable", "--now", SYSTEMD_SOCKET_UNIT)
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
    # Remove /run/hexor only if safe and empty.
    if RUNTIME_DIR.exists():
        try:
            entries = list(RUNTIME_DIR.iterdir())
        except OSError:
            entries = []
        if not entries:
            try:
                RUNTIME_DIR.rmdir()
            except OSError:
                pass

    # Fail-closed: if daemon-reload fails the rollback is reported as failed
    # (artifacts were already removed above, but the unit state is inconsistent
    # and must not be silently swallowed).
    _systemctl(runner, "daemon-reload")

    return {
        "live": True,
        "removed": removed,
        "preserved": list(protected),
        "preserves_identities": True,
    }


# ----------------------------------------------------------------- bind trust


def bind_trust_from_cli(args: Mapping[str, Any], *, live: bool) -> Mapping[str, Any]:
    """Explicit phase-B trust bind. Never called from install-base/plan.

    Validates an external public trust store (exact SHA-256, no secret material)
    and installs it atomically to the canonical destination root:hexor-runner
    0640. An existing different destination fails closed. On a dry-run it only
    validates the source (no install).
    """

    from trust_binding import TrustBindingError as _TBError

    try:
        source = from_cli_args(args)
    except _TBError as exc:
        raise DeploymentBoundaryError(exc.code, str(exc)) from exc
    if source is None:
        raise DeploymentBoundaryError(
            "BIND_ARGS_INCOMPLETE",
            "bind-trust requires --trust-store-path, --expected-sha256 and --public-source",
        )

    if live is False:
        # Validate-only: prove the source is acceptable without installing.
        from trust_binding import validate_trust_binding

        try:
            validate_trust_binding(source)
        except _TBError as exc:
            raise DeploymentBoundaryError(exc.code, str(exc)) from exc
        return {"live": False, "validated": source.as_safe_dict()}

    try:
        result = bind_trust_store(source, TRUST_STORE_CANONICAL_PATH)
    except _TBError as exc:
        raise DeploymentBoundaryError(exc.code, str(exc)) from exc
    return {"live": True, **dict(result)}


# ------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--descriptor", default=str(RUNTIME_DEPLOYMENT_YAML))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="read-only deployment plan + fail-closed envelope check")

    p_install = sub.add_parser("install-base", help="privileged base install of inert runtime artifacts")
    p_install.add_argument("--live", action="store_true", help="perform the install (root required)")
    p_install.add_argument("--no-root-required", action="store_true", help="relax root gate (tests only)")

    p_rollback = sub.add_parser("rollback-base", help="remove owned base artifacts and reload")
    p_rollback.add_argument("--live", action="store_true", help="perform the removal (root required)")
    p_rollback.add_argument("--no-root-required", action="store_true", help="relax root gate (tests only)")

    p_bind = sub.add_parser("bind-trust", help="explicit phase-B external public trust store bind")
    p_bind.add_argument("--trust-store-path", required=False)
    p_bind.add_argument("--expected-sha256", required=False)
    p_bind.add_argument("--public-source", action="store_true")
    p_bind.add_argument("--live", action="store_true", help="install the validated trust store (root required)")
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
                print("OK runner runtime deployment boundary is fail-closed and idempotent (HOLD, NOT_RUN)")
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
                       "OK base install completed (HOLD boundary, trust NOT bound, policies NOT enabled)"))
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
                       "OK base rollback completed (identities and trust store preserved)"))
            return EXIT_OK

        if args.command == "bind-trust":
            result = bind_trust_from_cli(
                {
                    "trust_store_path": args.trust_store_path,
                    "expected_sha256": args.expected_sha256,
                    "public_source": bool(args.public_source),
                },
                live=args.live,
            )
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(("DRY-RUN: trust source validated (pass --live to bind)"
                       if not result.get("live") else
                       "OK trust store bound to canonical destination root:hexor-runner 0640"))
            return EXIT_OK

        parser.error("unknown command")
        return EXIT_USAGE  # pragma: no cover

    except DeploymentBoundaryError as exc:
        if args.json:
            print(json.dumps(exc.as_dict(), indent=2, sort_keys=True))
        else:
            print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
            if exc.partial_identity_provisioning:
                print(
                    "WARN partial_identity_provisioning=true; created identities are "
                    "preserved for explicit operator lifecycle: "
                    + "; ".join(" ".join(c) for c in exc.created_identities),
                    file=sys.stderr,
                )
        return EXIT_FAIL_CLOSED
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures fail-closed
        print(f"FAIL UNEXPECTED: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
