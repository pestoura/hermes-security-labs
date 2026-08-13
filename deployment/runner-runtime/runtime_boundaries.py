#!/usr/bin/env python3
"""Fail-closed, idempotent Runner runtime deployment boundary constants.

This module is the single source of truth for the *repository-only* Runner
runtime deployment boundary implemented by ``#354``. It deliberately contains
only inert data and pure helpers. It never reads the live host, never provisions
a user/group/socket/service and never imports ``socket`` or any canonical
runtime module that would perform live work.

The boundary is HOLD by construction:

- policies are ``DISABLED`` / default-deny / ``runtime_status=NOT_RUN`` /
  ``execution_authority=none`` / ``promotion_allowed=false``;
- the listener may only derive kernel ``SO_PEERCRED`` from an accepted
  ``AF_UNIX`` peer and close/refuse; it never reads payloads, authorizes,
  creates receipts, calls the router, adapter or Evidence Plane, or touches a
  target;
- trust binding is phase B and is only ever accepted from an explicit external
  source with a public trust store and an expected SHA-256, validated
  fail-closed.

The declared Linux identities (``hexor-gateway`` 4100, ``hexor-runner`` 4101,
``hexor-dispatch`` 4110) and the ``/run/hexor`` socket ownership/mode mirror the
canonical example descriptor ``runner-identity-descriptor.example.yaml`` so the
two stay consistent. No live host identity is created here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

# Sibling import without package context (loaded standalone by tests/templates).
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from trust_binding import TrustBindingSource  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNTIME_DEPLOYMENT_YAML = HERE / "runtime-deployment.yaml"

# Canonical example descriptor identities (DO NOT diverge).
HEXOR_GATEWAY_UID = 4100
HEXOR_GATEWAY_GID = 4100
HEXOR_RUNNER_UID = 4101
HEXOR_RUNNER_GID = 4101
HEXOR_DISPATCH_GID = 4110

HEXOR_GATEWAY_USER = "hexor-gateway"
HEXOR_RUNNER_USER = "hexor-runner"
HEXOR_DISPATCH_GROUP = "hexor-dispatch"

# Runtime directory + AF_UNIX socket declaration (HOLD boundary surface).
RUNTIME_DIR_PATH = "/run/hexor"
RUNTIME_DIR_MODE = "0750"
SOCKET_PATH = "/run/hexor/runner-dispatch.sock"
SOCKET_MODE = "0660"

SOCKET_RELATIVE_PATH = "runner-dispatch.sock"
SYSTEMD_SOCKET_UNIT = "hexor-runner.socket"
SYSTEMD_SERVICE_UNIT = "hexor-runner.service"
TMPFILES_CONF = "hexor-runner.conf"
TRUST_STORE_PATH = "/etc/hexor/runner/authorization-trust-store.json"

# Canonical destination owner/mode for an explicitly-bound public trust store
# (phase B): root-owned, group hexor-runner, mode 0640 (read-only to the group).
TRUST_STORE_OWNER_UID = 0
TRUST_STORE_OWNER_GID = HEXOR_RUNNER_GID
TRUST_STORE_MODE = 0o0640

# Fail-closed policy envelope (never promoted by this boundary).
POLICY_STATE = "DISABLED"
POLICY_DEFAULT = "deny"
POLICY_RUNTIME_STATUS = "NOT_RUN"
POLICY_EXECUTION_AUTHORITY = "none"
PROMOTION_ALLOWED = False

DECLARED_IDENTITY_IDS = (HEXOR_GATEWAY_UID, HEXOR_GATEWAY_GID, HEXOR_RUNNER_UID, HEXOR_RUNNER_GID, HEXOR_DISPATCH_GID)
DECLARED_PRINCIPAL_NAMES = (HEXOR_GATEWAY_USER, HEXOR_RUNNER_USER, HEXOR_DISPATCH_GROUP)

# Canonical OS identity boundary (mirror runner-identity-descriptor.example.yaml).
HEXOR_NOLOGIN_SHELL = "/usr/sbin/nologin"
CANONICAL_DISPATCH_MEMBERS = (HEXOR_GATEWAY_USER, HEXOR_RUNNER_USER)


class BoundaryPhase(str, Enum):
    """Repository-only implementation phases for #354."""

    A = "base-hold-deployment"  # this implementation
    B = "trust-binding"  # deferred: explicit external trust store only


@dataclass(frozen=True)
class Identity:
    uid: int
    gid: int
    name: str
    kind: str  # "user" | "group"


@dataclass(frozen=True)
class SocketDeclaration:
    directory_path: str
    directory_mode: str
    directory_owner_uid: int
    directory_group_gid: int
    socket_path: str
    socket_mode: str
    socket_owner_uid: int
    socket_group_gid: int


@dataclass(frozen=True)
class UserSpec:
    """Canonical dedicated user identity (private group, nologin, no home)."""

    name: str
    uid: int
    gid: int
    shell: str
    home: str | None = None


@dataclass(frozen=True)
class GroupSpec:
    """Canonical dedicated group identity."""

    name: str
    gid: int


class IdentityStatus(str, Enum):
    """Outcome of assessing one canonical identity against a host probe."""

    EXACT = "exact"  # already present and byte-identical to the canonical spec
    ABSENT = "absent"  # not present; safe to provision (groupadd/useradd/usermod)
    CONFLICT = "conflict"  # name<->id mismatch or wrong gid/shell -> fail closed


CANONICAL_USERS = (
    UserSpec(HEXOR_GATEWAY_USER, HEXOR_GATEWAY_UID, HEXOR_GATEWAY_GID, HEXOR_NOLOGIN_SHELL),
    UserSpec(HEXOR_RUNNER_USER, HEXOR_RUNNER_UID, HEXOR_RUNNER_GID, HEXOR_NOLOGIN_SHELL),
)

# Private per-user groups come first (they are the primary GID of each user),
# then the shared dispatch group. This tuple order is the canonical provisioning
# order for ``groupadd``.
HEXOR_GATEWAY_GROUP = HEXOR_GATEWAY_USER
HEXOR_RUNNER_GROUP = HEXOR_RUNNER_USER
CANONICAL_GROUPS = (
    GroupSpec(HEXOR_GATEWAY_GROUP, HEXOR_GATEWAY_GID),
    GroupSpec(HEXOR_RUNNER_GROUP, HEXOR_RUNNER_GID),
    GroupSpec(HEXOR_DISPATCH_GROUP, HEXOR_DISPATCH_GID),
)

# Canonical name owners per *namespace*. UID and GID namespaces are distinct:
# uid 4100 and gid 4100 are both expected and are NOT a duplicate collision.
CANONICAL_UID_OWNERS = {
    HEXOR_GATEWAY_UID: HEXOR_GATEWAY_USER,
    HEXOR_RUNNER_UID: HEXOR_RUNNER_USER,
}
CANONICAL_GID_OWNERS = {
    HEXOR_GATEWAY_GID: HEXOR_GATEWAY_GROUP,
    HEXOR_RUNNER_GID: HEXOR_RUNNER_GROUP,
    HEXOR_DISPATCH_GID: HEXOR_DISPATCH_GROUP,
}


def declared_identities() -> tuple[Identity, ...]:
    return (
        Identity(HEXOR_GATEWAY_UID, HEXOR_GATEWAY_GID, HEXOR_GATEWAY_USER, "user"),
        Identity(HEXOR_RUNNER_UID, HEXOR_RUNNER_GID, HEXOR_RUNNER_USER, "user"),
        Identity(HEXOR_DISPATCH_GID, HEXOR_DISPATCH_GID, HEXOR_DISPATCH_GROUP, "group"),
    )


def declared_socket() -> SocketDeclaration:
    return SocketDeclaration(
        directory_path=RUNTIME_DIR_PATH,
        directory_mode=RUNTIME_DIR_MODE,
        directory_owner_uid=HEXOR_RUNNER_UID,
        directory_group_gid=HEXOR_DISPATCH_GID,
        socket_path=SOCKET_PATH,
        socket_mode=SOCKET_MODE,
        socket_owner_uid=HEXOR_RUNNER_UID,
        socket_group_gid=HEXOR_DISPATCH_GID,
    )


def fail_closed_policy_envelope() -> dict[str, Any]:
    """Return the canonical HOLD policy envelope. Idempotent data only."""

    return {
        "state": POLICY_STATE,
        "default": POLICY_DEFAULT,
        "runtime_status": POLICY_RUNTIME_STATUS,
        "execution_authority": POLICY_EXECUTION_AUTHORITY,
        "promotion_allowed": PROMOTION_ALLOWED,
    }


def no_target_effect_contract() -> set[str]:
    """Prohibited effects for the HOLD listener (phase A)."""

    return {
        "read_request_payload",
        "authorize_execution",
        "create_receipt",
        "call_router",
        "call_adapter",
        "touch_evidence_plane",
        "touch_target",
        "enable_trust_store",
    }


def detect_reserved_id_collision(
    observed_uids: Mapping[int, str] | None = None,
    observed_gids: Mapping[int, str] | None = None,
) -> list[str]:
    """Exact-aware, namespace-aware collision preflight for the boundary IDs.

    The UID and GID namespaces are **distinct**: uid 4100 (``hexor-gateway``
    user) and gid 4100 (``hexor-gateway`` private group) are both expected and
    are never reported as a duplicate collision.

    A reserved id is a CONFLICT only when it is already held, *in its own
    namespace*, by a name other than the canonical owner. An exact existing
    canonical identity (right id, right name) is idempotent and produces no
    finding.

    ``observed_uids`` / ``observed_gids`` map an integer id -> resolved name on
    the candidate host. When only the first mapping is supplied it is checked
    against both namespaces (backwards-compatible single-map call form).
    """

    findings: list[str] = []
    uids = dict(observed_uids or {})
    gids = dict(observed_gids or {})
    single_map = observed_gids is None

    def _check(namespace: str, observed: Mapping[int, str], canonical: Mapping[int, str]) -> None:
        for reserved_id, canonical_name in canonical.items():
            existing = observed.get(reserved_id)
            if existing is None or existing == canonical_name:
                continue  # absent (provisionable) or exact (idempotent)
            findings.append(
                f"id-collision: reserved {namespace} {reserved_id} is already held by "
                f"'{existing}' (canonical owner is '{canonical_name}'); deployment must "
                f"not reuse a conflicting OS identity"
            )

    _check("uid", uids, CANONICAL_UID_OWNERS)
    _check("gid", gids if not single_map else uids, CANONICAL_GID_OWNERS)
    # De-duplicate while preserving order (single-map form can double-report).
    unique: list[str] = []
    for finding in findings:
        if finding not in unique:
            unique.append(finding)
    return unique


def _assess_user(spec: UserSpec, by_uid: Mapping[str, Any] | None, by_name: Mapping[str, Any] | None) -> tuple[IdentityStatus, str]:
    if by_uid is None and by_name is None:
        return IdentityStatus.ABSENT, f"{spec.name} (uid {spec.uid}) not present"
    if by_uid is not None and by_uid.get("name") != spec.name:
        return IdentityStatus.CONFLICT, f"uid {spec.uid} already held by '{by_uid.get('name')}'"
    if by_name is not None and by_name.get("uid") != spec.uid:
        return IdentityStatus.CONFLICT, f"name {spec.name} already held by uid {by_name.get('uid')}"
    for observed in (by_uid, by_name):
        if observed is None:
            continue
        if observed.get("gid") != spec.gid:
            return IdentityStatus.CONFLICT, f"{spec.name} primary gid {observed.get('gid')} != canonical {spec.gid}"
        if observed.get("shell") != spec.shell:
            return IdentityStatus.CONFLICT, f"{spec.name} shell {observed.get('shell')} != canonical {spec.shell}"
    return IdentityStatus.EXACT, f"{spec.name} (uid {spec.uid}) exact match"


def _assess_group(spec: GroupSpec, by_gid: Mapping[str, Any] | None, by_name: Mapping[str, Any] | None) -> tuple[IdentityStatus, str]:
    if by_gid is None and by_name is None:
        return IdentityStatus.ABSENT, f"{spec.name} (gid {spec.gid}) not present"
    if by_gid is not None and by_gid.get("name") != spec.name:
        return IdentityStatus.CONFLICT, f"gid {spec.gid} already held by '{by_gid.get('name')}'"
    if by_name is not None and by_name.get("gid") != spec.gid:
        return IdentityStatus.CONFLICT, f"name {spec.name} already held by gid {by_name.get('gid')}"
    return IdentityStatus.EXACT, f"{spec.name} (gid {spec.gid}) exact match"


def preflight_identities(
    user_by_uid,
    user_by_name,
    group_by_gid,
    group_by_name,
    group_members=None,
) -> list[tuple[str, str, IdentityStatus, str]]:
    """Assess every canonical identity against host probes (fail-closed).

    Both the *name* and the *id* of every canonical object are examined before
    any mutation is considered. Returns a list of ``(kind, name, status, detail)``
    tuples where ``kind`` is ``"group"``, ``"user"`` or ``"membership"``:

    - ``EXACT``    : already present and identical to the canonical spec ->
                     idempotent PASS, nothing to provision;
    - ``ABSENT``   : safe to provision (``groupadd`` / ``useradd`` / ``usermod``);
    - ``CONFLICT`` : same name with a wrong id/shell/primary gid, or the reserved
                     id already owned by another name -> fail closed, RED. A
                     conflicting id is never reused.

    Groups are assessed before users (a user's private group must exist first)
    and supplementary ``hexor-dispatch`` membership is assessed last.
    ``group_members`` is an optional callable ``name -> sequence[str] | None``
    returning the supplementary member list of a group.
    """

    results: list[tuple[str, str, IdentityStatus, str]] = []
    for gspec in CANONICAL_GROUPS:
        status, detail = _assess_group(gspec, group_by_gid(gspec.gid), group_by_name(gspec.name))
        results.append(("group", gspec.name, status, detail))
    for uspec in CANONICAL_USERS:
        status, detail = _assess_user(uspec, user_by_uid(uspec.uid), user_by_name(uspec.name))
        results.append(("user", uspec.name, status, detail))

    if group_members is not None:
        members = group_members(HEXOR_DISPATCH_GROUP)
        member_set = set(members or ())
        for user in CANONICAL_DISPATCH_MEMBERS:
            if user in member_set:
                results.append((
                    "membership", user, IdentityStatus.EXACT,
                    f"{user} is already a member of {HEXOR_DISPATCH_GROUP}",
                ))
            else:
                results.append((
                    "membership", user, IdentityStatus.ABSENT,
                    f"{user} is not yet a member of {HEXOR_DISPATCH_GROUP}",
                ))
    return results


def identity_conflicts(results) -> list[str]:
    """Return the CONFLICT details from a ``preflight_identities`` result set."""

    return [
        f"identity-conflict: {kind} {name}: {detail}"
        for kind, name, status, detail in results
        if status is IdentityStatus.CONFLICT
    ]


def plan_identity_provisioning(results) -> list[list[str]]:
    """Deterministic provisioning command plan for ABSENT objects only.

    Order is fixed and never reuses a conflicting id:

    1. ``groupadd --gid 4100 hexor-gateway``
    2. ``groupadd --gid 4101 hexor-runner``
    3. ``groupadd --gid 4110 hexor-dispatch``
    4. ``useradd ... hexor-gateway``
    5. ``useradd ... hexor-runner``
    6. ``usermod --append --groups hexor-dispatch <user>``

    EXACT objects yield no command (idempotent no-op). Raises ``ValueError`` when
    the result set still contains a CONFLICT: provisioning is never planned over
    a RED preflight.
    """

    conflicts = identity_conflicts(results)
    if conflicts:
        raise ValueError("; ".join(conflicts))

    absent = {(kind, name) for kind, name, status, _d in results if status is IdentityStatus.ABSENT}
    commands: list[list[str]] = []
    for gspec in CANONICAL_GROUPS:
        if ("group", gspec.name) in absent:
            commands.append(["groupadd", "--gid", str(gspec.gid), gspec.name])
    for uspec in CANONICAL_USERS:
        if ("user", uspec.name) in absent:
            commands.append([
                "useradd",
                "--uid", str(uspec.uid),
                "--gid", str(uspec.gid),
                "--no-create-home",
                "--home-dir", "/nonexistent",
                "--shell", uspec.shell,
                "--no-user-group",
                uspec.name,
            ])
    for user in CANONICAL_DISPATCH_MEMBERS:
        if ("membership", user) in absent:
            commands.append(["usermod", "--append", "--groups", HEXOR_DISPATCH_GROUP, user])
    return commands


def validate_trust_binding_present(source: TrustBindingSource | None) -> None:
    """Reject any trust binding that is not an explicit, validated external source.

    Phase A never installs a trust store. Phase B only accepts a binding built
    from an explicit external source with a public trust store and an expected
    SHA-256, validated fail-closed (see ``trust_binding.validate_trust_binding``).
    """

    if source is None:
        # Phase A: no trust binding at all. This is the safe default.
        return
    # Imported lazily so the base boundary never depends on live validation.
    # Sibling import (no package-relative import: this directory is not a package).
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import trust_binding as _tb  # noqa: E402

    _tb.validate_trust_binding(source)
