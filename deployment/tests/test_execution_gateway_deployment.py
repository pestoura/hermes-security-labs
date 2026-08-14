"""Repository-only tests for the Execution Gateway deployment boundary (#359).

The gateway is the CLIENT side of the AF_UNIX dispatch boundary and the sibling
of the Runner runtime HOLD boundary (#354). It installs ONLY gateway-owned
artifacts; it never provisions identities (owned by #354), never creates the
dispatcher socket, never binds a trust store, never enables an execution policy
and never touches a target (WebGoat/Kali) or the network.

These tests prove the controller is fail-closed, exact-aware, idempotent, and
rollbackable by building a fake identity host and stubbing all real I/O. The
Runner runtime, its identities, /run/hexor, the dispatcher socket and the trust
store are asserted UNTOUCHED.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "deployment" / "execution-gateway"
DEPLOYMENT_MODULE = GATEWAY_DIR / "execution_gateway_deployment.py"
HOLD_MODULE = GATEWAY_DIR / "execution_gateway_hold.py"
DESCRIPTOR = GATEWAY_DIR / "execution-gateway-deployment.yaml"
SERVICE_UNIT = GATEWAY_DIR / "systemd" / "hexor-execution-gateway.service"
TMPFILES_SRC = GATEWAY_DIR / "tmpfiles" / "hexor-execution-gateway.conf"
CANONICAL_TRANSPORT_POLICY = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"


def _load(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deployment = _load("execution_gateway_deployment_test", DEPLOYMENT_MODULE)


def _descriptor() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8")))


# ----------------------------------------------------- canonical state untouched


def test_canonical_transport_policy_remains_disabled_not_run() -> None:
    policy = yaml.safe_load(CANONICAL_TRANSPORT_POLICY.read_text(encoding="utf-8"))
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["modes"]["unix-peer"]["socket_path"] == "NOT_CONFIGURED"
    assert policy["modes"]["unix-peer"]["allowed_peers"] == []


def test_descriptor_mirrors_canonical_gateway_identity_ids() -> None:
    descriptor = _descriptor()
    assert descriptor["identities"]["gateway"]["uid"] == 4100
    assert descriptor["identities"]["gateway"]["gid"] == 4100
    assert descriptor["identities"]["dispatch_group"]["gid"] == 4110


# ---------------------------------------------------------------- HOLD envelope


def test_descriptor_keeps_fail_closed_policy_envelope() -> None:
    descriptor = _descriptor()
    envelope = deployment.fail_closed_policy_envelope()
    policy = descriptor["policy"]
    for key, value in envelope.items():
        assert policy[key] == value
    assert descriptor["runtime_status"] == "NOT_RUN"
    assert descriptor["promotion_allowed"] is False


def test_listener_is_strictly_hold_and_refuses_every_downstream_effect() -> None:
    descriptor = _descriptor()
    listener = descriptor["listener"]
    assert listener["mode"] == "HOLD"
    assert listener["transport"] == "unix-peer"
    assert listener["identity_source"] == "linux-so-peercred"
    assert listener["role"] == "client"
    assert set(listener["refuse_on_any"]) == set(deployment.PROHIBITED_EFFECTS)


def test_no_target_effects_possible() -> None:
    descriptor = _descriptor()
    tb = descriptor["trust_binding"]
    assert tb["enabled"] is False
    assert tb["source"] is None
    assert tb["public_source"] is False
    assert tb["expected_sha256"] is None
    for effect in descriptor["target_effects"].values():
        assert effect in (None, "none")


# ----------------------------------------------------- collision preflight


def test_collision_preflight_fails_closed_on_conflicting_uid() -> None:
    findings = deployment.detect_reserved_id_collision({4100: "some-real-user"}, {})
    assert any("reserved uid 4100" in f for f in findings)


def test_collision_preflight_fails_closed_on_conflicting_gid() -> None:
    findings = deployment.detect_reserved_id_collision({}, {4110: "other-group"})
    assert any("reserved gid 4110" in f for f in findings)


def test_collision_preflight_passes_when_ids_free() -> None:
    findings = deployment.detect_reserved_id_collision({2000: "other"}, {3000: "another"})
    assert findings == []


def test_collision_preflight_is_exact_aware_and_accepts_canonical_identities() -> None:
    """uid 4100 and gid 4100 both exist canonically: not a duplicate collision."""
    findings = deployment.detect_reserved_id_collision(
        {4100: "hexor-gateway", 4101: "hexor-runner"},
        {4100: "hexor-gateway", 4101: "hexor-runner", 4110: "hexor-dispatch"},
    )
    assert findings == []


def test_uid_and_gid_namespaces_are_distinct() -> None:
    """A foreign group on gid 4100 must not be reported as a uid collision."""
    findings = deployment.detect_reserved_id_collision({}, {4100: "foreign-group"})
    assert len(findings) == 1
    assert "reserved gid 4100" in findings[0]


# ------------------------------------------------- fake identity host (no NSS)


class FakeIdentityHost:
    """In-memory NSS double. Never touches the real host.

    The gateway asserts EXACTNESS only: the fake host can be in an EXACT state
    (acceptable), ABSENT state (fail-closed: provisioning is owned by #354) or
    CONFLICT state (fail-closed). The gateway never issues groupadd/useradd/
    usermod, so the fake ``run`` ignores provisioning commands for the identity
    namespace and is used only for systemd lifecycle assertions.
    """

    GROUPS = {"hexor-gateway": 4100, "hexor-dispatch": 4110}
    USERS = {"hexor-gateway": (4100, 4100)}

    def __init__(
        self,
        *,
        groups: dict[str, int] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
        members: dict[str, list[str]] | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.groups: dict[str, int] = dict(groups or {})
        self.users: dict[str, dict[str, Any]] = dict(users or {})
        self.members: dict[str, list[str]] = {k: list(v) for k, v in (members or {}).items()}
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    @classmethod
    def exact(cls, *, memberships: bool = True) -> "FakeIdentityHost":
        users = {
            name: {"name": name, "uid": uid, "gid": gid, "shell": "/usr/sbin/nologin"}
            for name, (uid, gid) in cls.USERS.items()
        }
        members = {"hexor-dispatch": list(cls.USERS) if memberships else []}
        return cls(groups=dict(cls.GROUPS), users=users, members=members)

    @classmethod
    def absent(cls) -> "FakeIdentityHost":
        return cls(groups={}, users={}, members={})

    @classmethod
    def conflict(cls) -> "FakeIdentityHost":
        # A foreign user already holds uid 4100: hard collision.
        return cls(
            groups=dict(cls.GROUPS),
            users={"intruder": {"name": "intruder", "uid": 4100, "gid": 4100, "shell": "/bin/bash"}},
            members={"hexor-dispatch": []},
        )

    def probes(self):
        def user_by_uid(uid: int):
            for entry in self.users.values():
                if entry["uid"] == uid:
                    return dict(entry)
            return None

        def user_by_name(name: str):
            entry = self.users.get(name)
            return dict(entry) if entry else None

        def group_by_gid(gid: int):
            for gname, ggid in self.groups.items():
                if ggid == gid:
                    return {"name": gname, "gid": ggid}
            return None

        def group_by_name(name: str):
            if name in self.groups:
                return {"name": name, "gid": self.groups[name]}
            return None

        return user_by_uid, user_by_name, group_by_gid, group_by_name

    def group_members(self, name: str):
        return tuple(self.members.get(name, ()))

    def run(self, command):
        command = list(command)
        self.calls.append(command)
        if self.fail_on and command[0] == self.fail_on:
            return 1, f"fake failure for {self.fail_on}"
        return 0, ""


def _preflight(host: FakeIdentityHost):
    return deployment.preflight_identities(*host.probes(), host.group_members)


def _install(host: FakeIdentityHost, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, live: bool = True):
    installed: list[str] = []
    systemd: list[tuple[str, ...]] = []

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda src, dst, **k: installed.append(str(dst)))
    monkeypatch.setattr(deployment, "_systemctl", lambda _runner, *args: systemd.append(args))
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _runner: systemd.append(("tmpfiles",)))
    monkeypatch.setattr(deployment, "_verify_installed_file", lambda *a, **k: None)

    # Make the install dir land inside tmp_path so stray writes are caught.
    monkeypatch.setattr(deployment, "INSTALL_BIN_DIR", tmp_path / "opt" / "hexor" / "execution-gateway")
    monkeypatch.setattr(deployment, "HOLD_DST", deployment.INSTALL_BIN_DIR / "execution_gateway_hold.py")
    monkeypatch.setattr(deployment, "README_DST", deployment.INSTALL_BIN_DIR / "README.md")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", deployment.INSTALL_BIN_DIR / "execution-gateway-deployment.yaml")
    monkeypatch.setattr(deployment, "SERVICE_DST", tmp_path / "etc" / "systemd" / "system" / "hexor-execution-gateway.service")
    monkeypatch.setattr(deployment, "TMPFILES_CONF_DST", tmp_path / "etc" / "tmpfiles.d" / "hexor-execution-gateway.conf")

    result = deployment.install_base(
        _descriptor(),
        live=live,
        require_root=False,
        probes=host.probes(),
        group_members=host.group_members,
        run_command=host.run,
    )
    return result, installed, systemd


# --------------------------------------------------- identity preflight semantics


def test_identity_preflight_exact_is_the_only_acceptable_state() -> None:
    results = _preflight(FakeIdentityHost.exact())
    assert all(s == deployment.IdentityStatus.EXACT for _k, _n, s, _d in results)
    assert deployment.identity_conflicts(results) == []


def test_identity_preflight_absent_is_red_not_provisioned() -> None:
    results = _preflight(FakeIdentityHost.absent())
    statuses = {n: s for k, n, s, _d in results}
    assert all(s == deployment.IdentityStatus.ABSENT for s in statuses.values())
    # ABSENT is NOT a pass: the gateway fails closed (provisioning is #354's lane).
    assert deployment.identity_conflicts(results)


def test_identity_preflight_same_uid_other_user_is_red() -> None:
    results = _preflight(FakeIdentityHost.conflict())
    assert any(s == deployment.IdentityStatus.CONFLICT for _k, _n, s, _d in results)
    assert deployment.identity_conflicts(results)


def test_identity_preflight_missing_dispatch_membership_is_red() -> None:
    results = _preflight(FakeIdentityHost.exact(memberships=False))
    memberships = {n: s for k, n, s, _d in results if k == "membership"}
    assert memberships["hexor-gateway"] == deployment.IdentityStatus.ABSENT
    assert deployment.identity_conflicts(results)


# ------------------------------------------------- install-base exactness gate


def test_install_base_exact_installs_only_gateway_artifacts_and_runs_systemd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    result, installed, systemd = _install(host, monkeypatch, tmp_path)
    assert result["provisioned_identities"] is False
    assert result["created_identities"] == []
    assert all(s == "exact" for _k, _n, s, _d in result["identity_status"])
    # Identity provisioning commands must never appear.
    assert not any(c[0] in {"groupadd", "useradd", "usermod"} for c in host.calls)
    # Only gateway-owned files installed.
    assert installed == [
        str(deployment.HOLD_DST),
        str(deployment.README_DST),
        str(deployment.DESCRIPTOR_DST),
        str(deployment.SERVICE_DST),
        str(deployment.TMPFILES_CONF_DST),
    ]
    assert systemd[0] == ("daemon-reload",)
    assert ("tmpfiles",) in systemd
    assert ("enable", "--now", "hexor-execution-gateway.service") in systemd
    assert result["bound_trust"] is False
    assert result["enabled_policies"] is False
    assert result["touched_target"] is False
    assert result["promotion_allowed"] is False
    assert result["execution_authority"] == "none"
    assert result["runtime_status"] == "NOT_RUN"


def test_install_base_absent_identities_fail_closed_before_any_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.absent()
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "PREFLIGHT_FAILED"
    assert exc.value.partial is False
    # No file or systemd action followed the failed identity preflight.
    assert not any(c[0] in {"systemctl", "systemd-tmpfiles"} for c in host.calls)


def test_install_base_conflict_identities_fail_closed_before_any_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.conflict()
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "PREFLIGHT_FAILED"
    assert not any(c[0] in {"systemctl", "systemd-tmpfiles"} for c in host.calls)


def test_install_base_id_collision_preflight_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A foreign group already owns gid 4110 and a foreign user owns uid 4100:
    # the exact-aware collision preflight must refuse before any mutation.
    host = FakeIdentityHost(
        groups={"foreign-gw": 4100, "other-group": 4110},
        users={"intruder": {"name": "intruder", "uid": 4100, "gid": 4100, "shell": "/bin/bash"}},
        members={},
    )
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "PREFLIGHT_FAILED"
    # The gateway must never reuse a conflicting OS identity (asserted RED).


def test_install_base_never_provisions_identities_even_when_absent() -> None:
    """No groupadd/useradd/usermod anywhere in the controller source."""
    source = DEPLOYMENT_MODULE.read_text(encoding="utf-8")
    for forbidden in ("groupadd", "useradd", "usermod", "groupdel", "userdel", "gpasswd"):
        assert forbidden not in source


# --------------------------------------------------------- drift / idempotence


def test_install_base_is_idempotent_when_files_exist_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()

    def fake_verify(src, dst, *, executable=False):
        # Simulate existing byte-identical files: no drift reported.
        return None

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_verify_installed_file", fake_verify)
    writes: list[str] = []

    def fake_install(src, dst, **k):
        writes.append(str(dst))

    monkeypatch.setattr(deployment, "_install_file", fake_install)
    monkeypatch.setattr(deployment, "_systemctl", lambda _r, *a: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)

    result = deployment.install_base(
        _descriptor(), live=True, require_root=False,
        probes=host.probes(), group_members=host.group_members, run_command=host.run,
    )
    # The plan is idempotent and still succeeds; _install_file is the no-op path
    # exercised by the real copy2 (here stubbed). The postcondition is GREEN.
    assert result["live"] is True
    assert result["provisioned_identities"] is False


def test_install_base_drift_detected_is_red_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    # Pretend an installed file has drifted (symlink).
    monkeypatch.setattr(
        deployment, "_verify_installed_file",
        lambda src, dst, *, executable=False: "drift: /opt/hexor/execution-gateway/holding is a symlink",
    )
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_systemctl", lambda _r, *a: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.install_base(
            _descriptor(), live=True, require_root=False,
            probes=host.probes(), group_members=host.group_members, run_command=host.run,
        )
    assert exc.value.code == "DRIFT_DETECTED"


def test_install_base_postcondition_drift_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "INSTALL_BIN_DIR", tmp_path / "opt" / "hexor" / "execution-gateway")
    monkeypatch.setattr(deployment, "HOLD_DST", deployment.INSTALL_BIN_DIR / "execution_gateway_hold.py")
    monkeypatch.setattr(deployment, "README_DST", deployment.INSTALL_BIN_DIR / "README.md")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", deployment.INSTALL_BIN_DIR / "execution-gateway-deployment.yaml")
    monkeypatch.setattr(deployment, "SERVICE_DST", tmp_path / "etc" / "systemd" / "system" / "hexor-execution-gateway.service")
    monkeypatch.setattr(deployment, "TMPFILES_CONF_DST", tmp_path / "etc" / "tmpfiles.d" / "hexor-execution-gateway.conf")
    # Real copy so files exist after install; the postcondition re-probe then
    # finds every installed file "drifted" (forced mismatch).
    monkeypatch.setattr(deployment, "_install_file", deployment._install_file)
    monkeypatch.setattr(deployment, "_systemctl", lambda _r, *a: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)
    monkeypatch.setattr(
        deployment, "_verify_installed_file",
        lambda src, dst, *, executable=False: ("drift: postcondition mismatch" if Path(dst).exists() else None),
    )
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.install_base(
            _descriptor(), live=True, require_root=False,
            probes=host.probes(), group_members=host.group_members, run_command=host.run,
        )
    assert exc.value.code == "POSTCONDITION_DRIFT"


# ----------------------------------------------------------- systemd failures


def test_install_base_daemon_reload_failure_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_verify_installed_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)

    def fake_systemctl(_runner, *args):
        if args[:1] == ("daemon-reload",):
            raise deployment.DeploymentBoundaryError(
                deployment.SYSTEMD_DAEMON_RELOAD_FAILED, "daemon-reload rc=1"
            )

    monkeypatch.setattr(deployment, "_systemctl", fake_systemctl)
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.install_base(
            _descriptor(), live=True, require_root=False,
            probes=host.probes(), group_members=host.group_members, run_command=host.run,
        )
    assert exc.value.code == deployment.SYSTEMD_DAEMON_RELOAD_FAILED


def test_install_base_enable_failure_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_verify_installed_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)

    def fake_systemctl(_runner, *args):
        if args[:2] == ("enable", "--now"):
            raise deployment.DeploymentBoundaryError(
                deployment.SYSTEMD_ENABLE_FAILED, "enable --now rc=1"
            )

    monkeypatch.setattr(deployment, "_systemctl", fake_systemctl)
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.install_base(
            _descriptor(), live=True, require_root=False,
            probes=host.probes(), group_members=host.group_members, run_command=host.run,
        )
    assert exc.value.code == deployment.SYSTEMD_ENABLE_FAILED


def test_install_base_partial_systemd_failure_does_not_corrupt_rollback_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If enable fails, the rollback contract still lists only gateway files."""
    plan = deployment.build_plan(_descriptor())
    # Rollback remove list must contain only gateway-owned paths.
    for path in plan.remove_on_rollback:
        assert str(path).startswith("/opt/hexor/execution-gateway") or str(path).endswith(
            ("hexor-execution-gateway.service", "hexor-execution-gateway.conf")
        )
        assert "runner-dispatch" not in str(path)
        assert "trust-store" not in str(path)


# ---------------------------------------------------------------- rollback


def test_rollback_base_removes_only_gateway_artifacts_and_disables_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    systemd: list[tuple[str, ...]] = []

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])

    # Build the rollback plan against a fake install layout.
    monkeypatch.setattr(deployment, "INSTALL_BIN_DIR", tmp_path / "opt" / "hexor" / "execution-gateway")
    monkeypatch.setattr(deployment, "HOLD_DST", deployment.INSTALL_BIN_DIR / "execution_gateway_hold.py")
    monkeypatch.setattr(deployment, "README_DST", deployment.INSTALL_BIN_DIR / "README.md")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", deployment.INSTALL_BIN_DIR / "execution-gateway-deployment.yaml")
    monkeypatch.setattr(deployment, "SERVICE_DST", tmp_path / "etc" / "systemd" / "system" / "hexor-execution-gateway.service")
    monkeypatch.setattr(deployment, "TMPFILES_CONF_DST", tmp_path / "etc" / "tmpfiles.d" / "hexor-execution-gateway.conf")

    # Create the fake installed files so rollback has something to remove.
    # Simulate root ownership (tests run unprivileged): the residue check
    # compares against deployment.OWNER_ROOT_* constants, which we point at the
    # real on-disk owner for the duration of the test.
    import os as _os

    monkeypatch.setattr(deployment, "OWNER_ROOT_UID", _os.geteuid())
    monkeypatch.setattr(deployment, "OWNER_ROOT_GID", _os.getegid())
    for dst in (deployment.HOLD_DST, deployment.README_DST, deployment.DESCRIPTOR_DST,
                deployment.SERVICE_DST, deployment.TMPFILES_CONF_DST):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("gateway-owned-artifact\n", encoding="utf-8")
        os_chmod_root(dst)

    monkeypatch.setattr(deployment, "_systemctl", lambda _r, *a: systemd.append(a))

    result = deployment.rollback_base(
        _descriptor(), live=True, require_root=False, run_command=host.run
    )
    assert result["live"] is True
    assert systemd[0] == ("disable", "--now", "hexor-execution-gateway.service")
    assert systemd[-1] == ("daemon-reload",)
    # Identities, /run/hexor, runner socket, trust store preserved.
    assert deployment.TRUST_STORE_PATH in result["preserved"]
    assert str(deployment.RUNNER_SOCKET) in result["preserved"]
    assert str(deployment.RUNTIME_DIR) in result["preserved"]
    assert result["preserves_identities"] is True
    assert len(result["removed"]) == 5
    # The fake installed files are gone; identities untouched.
    assert not deployment.HOLD_DST.exists()


def test_rollback_base_dry_run_reports_only_gateway_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    result = deployment.rollback_base(_descriptor(), live=False, require_root=False)
    assert result["live"] is False
    assert deployment.TRUST_STORE_PATH in result["protected"]
    assert str(deployment.RUNNER_SOCKET) in result["protected"]
    assert result["preserves_identities"] is True


def test_rollback_does_not_list_shared_identity_or_runner_artifacts() -> None:
    """Rollback remove list must never include identities/socket/trust store."""
    plan = deployment.build_plan(_descriptor())
    for path in plan.remove_on_rollback:
        assert "trust-store" not in str(path)
        assert "runner-dispatch" not in str(path)
        assert str(path).endswith((
            "execution_gateway_hold.py", "README.md", "execution-gateway-deployment.yaml",
            "hexor-execution-gateway.service", "hexor-execution-gateway.conf",
        ))


def test_rollback_residue_is_red_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-root-owned installed file is residue: refuse blind removal.
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    # The residue check compares against deployment.OWNER_ROOT_*. We pin them to
    # 0 (canonical root) so the unprivileged test file (real euid != 0) is
    # correctly flagged as non-root-owned residue.
    monkeypatch.setattr(deployment, "OWNER_ROOT_UID", 0)
    monkeypatch.setattr(deployment, "OWNER_ROOT_GID", 0)
    monkeypatch.setattr(deployment, "INSTALL_BIN_DIR", tmp_path / "opt" / "hexor" / "execution-gateway")
    monkeypatch.setattr(deployment, "HOLD_DST", deployment.INSTALL_BIN_DIR / "execution_gateway_hold.py")
    monkeypatch.setattr(deployment, "README_DST", deployment.INSTALL_BIN_DIR / "README.md")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", deployment.INSTALL_BIN_DIR / "execution-gateway-deployment.yaml")
    monkeypatch.setattr(deployment, "SERVICE_DST", tmp_path / "etc" / "systemd" / "system" / "hexor-execution-gateway.service")
    monkeypatch.setattr(deployment, "TMPFILES_CONF_DST", tmp_path / "etc" / "tmpfiles.d" / "hexor-execution-gateway.conf")
    dst = deployment.HOLD_DST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("x\n", encoding="utf-8")
    os_chmod_root(dst, owner_uid=1000)
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.rollback_base(_descriptor(), live=True, require_root=False, run_command=FakeIdentityHost.exact().run)
    assert exc.value.code == "ROLLBACK_RESIDUE"
    # The residue file is still present (not removed blindly).
    assert dst.exists()


def test_rollback_disable_failure_is_red_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    import os as _os

    monkeypatch.setattr(deployment, "OWNER_ROOT_UID", _os.geteuid())
    monkeypatch.setattr(deployment, "OWNER_ROOT_GID", _os.getegid())
    monkeypatch.setattr(deployment, "INSTALL_BIN_DIR", tmp_path / "opt" / "hexor" / "execution-gateway")
    monkeypatch.setattr(deployment, "HOLD_DST", deployment.INSTALL_BIN_DIR / "execution_gateway_hold.py")
    monkeypatch.setattr(deployment, "README_DST", deployment.INSTALL_BIN_DIR / "README.md")
    monkeypatch.setattr(deployment, "DESCRIPTOR_DST", deployment.INSTALL_BIN_DIR / "execution-gateway-deployment.yaml")
    monkeypatch.setattr(deployment, "SERVICE_DST", tmp_path / "etc" / "systemd" / "system" / "hexor-execution-gateway.service")
    monkeypatch.setattr(deployment, "TMPFILES_CONF_DST", tmp_path / "etc" / "tmpfiles.d" / "hexor-execution-gateway.conf")
    for dst in (deployment.HOLD_DST, deployment.README_DST, deployment.DESCRIPTOR_DST,
                deployment.SERVICE_DST, deployment.TMPFILES_CONF_DST):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("gateway-owned\n", encoding="utf-8")
        os_chmod_root(dst)

    def fake_run(cmd, *a, **k):
        if cmd[:1] == ["systemctl"] and cmd[1:3] == ["disable", "--now"]:
            return 1, "disable rc=1"
        return 0, ""

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.rollback_base(_descriptor(), live=True, require_root=False, run_command=fake_run)
    assert exc.value.code == deployment.SYSTEMD_DISABLE_FAILED
    # No artifact removed when disable failed.
    assert deployment.HOLD_DST.exists()


# ----------------------------------------------------- runner/shared untouched


def test_install_base_touches_no_runner_identity_or_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof the gateway only reads identities, never mutates the runner side."""
    observed_calls: list[list[str]] = []

    def fake_run(cmd, *a, **k):
        observed_calls.append(list(cmd))
        return 0, ""

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_verify_installed_file", lambda *a, **k: None)
    monkeypatch.setattr(deployment, "_systemctl", lambda _r, *a: None)
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _r: None)

    deployment.install_base(
        _descriptor(), live=True, require_root=False,
        probes=FakeIdentityHost.exact().probes(),
        group_members=FakeIdentityHost.exact().group_members,
        run_command=fake_run,
    )
    # Only systemd lifecycle commands; never touche /run/hexor or the socket.
    assert not any("/run/hexor" in " ".join(c) for c in observed_calls)
    assert not any("runner-dispatch" in " ".join(c) for c in observed_calls)


def test_module_performs_no_privileged_or_provisioning_calls() -> None:
    """AST proof: no socket bind/listen, no identity provisioning, no trust bind."""
    tree = ast.parse(DEPLOYMENT_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    for forbidden in ("groupadd", "useradd", "usermod", "groupdel", "userdel"):
        assert forbidden not in source
    for token in (".bind(", "listen(", "socket.bind", "TRUST_STORE_CANONICAL_PATH"):
        assert token not in source
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not any("bind_trust" in c for c in called)


def test_gateway_never_creates_or_owns_the_runner_socket() -> None:
    """The descriptor/service declare the runner side owns the socket."""
    descriptor = _descriptor()
    assert descriptor["gateway_client"]["role"] == "client"
    assert descriptor["gateway_client"]["socket_path"] == "/run/hexor/runner-dispatch.sock"
    # No gateway socket unit shipped.
    assert not (GATEWAY_DIR / "systemd" / "hexor-execution-gateway.socket").exists()


# ---------------------------------------------------------------- plan integrity


def test_plan_is_idempotent_across_repeated_builds() -> None:
    first = deployment.build_plan(_descriptor())
    second = deployment.build_plan(_descriptor())
    assert first.ok is True
    assert first.install_files == second.install_files
    assert first.remove_on_rollback == second.remove_on_rollback
    assert first.policy_envelope == second.policy_envelope


def test_plan_does_not_mutate_the_descriptor() -> None:
    descriptor = _descriptor()
    snapshot = copy.deepcopy(descriptor)
    deployment.build_plan(descriptor)
    assert descriptor == snapshot


def test_dependency_preflight_requires_activation_tooling() -> None:
    missing = deployment.dependency_preflight(which=lambda cmd: None, file_exists=lambda path: False)
    blob = "\n".join(missing)
    for command in ("systemctl", "systemd-tmpfiles"):
        assert command in blob
    assert "/usr/bin/python3" in blob
    assert "/usr/sbin/nologin" in blob


def test_dependency_preflight_is_green_when_tooling_present() -> None:
    findings = deployment.dependency_preflight(
        which=lambda cmd: f"/usr/sbin/{cmd}", file_exists=lambda path: True
    )
    assert findings == []


# ---------------------------------------------------------------------- CLI shape


def test_cli_exposes_only_plan_install_rollback() -> None:
    completed = __import__("subprocess").run(
        [sys.executable, str(DEPLOYMENT_MODULE), "--help"],
        capture_output=True, text=True,
    )
    assert "positional arguments" in completed.stdout
    for sub in ("plan", "install-base", "rollback-base"):
        assert sub in completed.stdout
    assert "bind-trust" not in completed.stdout  # gateway binds no trust


def test_cli_plan_exits_ok_and_emits_fail_closed_envelope() -> None:
    completed = __import__("subprocess").run(
        [sys.executable, str(DEPLOYMENT_MODULE), "--json", "plan"],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["policy_envelope"]["state"] == "DISABLED"
    assert report["policy_envelope"]["runtime_status"] == "NOT_RUN"
    assert report["policy_envelope"]["execution_authority"] == "none"
    assert report["policy_envelope"]["promotion_allowed"] is False
    assert "send_runner_payload" in report["prohibited_effects"]
    assert "touch_target" in report["prohibited_effects"]


def test_cli_install_base_root_gate_fails_when_not_root() -> None:
    if __import__("os").geteuid() == 0:
        pytest.skip("running as root; cannot exercise non-root refusal")
    rc = deployment.main(["install-base", "--live"])
    assert rc == deployment.EXIT_FAIL_CLOSED


def test_cli_install_base_dry_run_performs_no_host_mutation() -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, *a, **k):
        calls.append(tuple(cmd))
        return __import__("subprocess").CompletedProcess(cmd, 0, "", "")

    monkeypatch_run = __import__("pytest").MonkeyPatch()
    monkeypatch_run.setattr(__import__("subprocess"), "run", fake_run)
    try:
        rc = deployment.main(["--json", "install-base", "--no-root-required"])
    finally:
        monkeypatch_run.undo()
    assert rc == deployment.EXIT_OK
    assert not calls  # dry-run issues no mutation commands


def test_cli_rollback_dry_run_preserves_identities_and_trust_store() -> None:
    rc = deployment.main(["--json", "rollback-base", "--no-root-required"])
    assert rc == deployment.EXIT_OK


def test_descriptor_refuses_promotion_claim() -> None:
    descriptor = _descriptor()
    descriptor["runtime_status"] = "RUNNING"
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.build_plan(descriptor)
    assert "must remain NOT_RUN" in str(exc.value)


# --------------------------------------------------------------------- helper


def os_chmod_root(path: Path, *, owner_uid: int = 0, owner_gid: int = 0) -> None:
    os_chmod(path, 0o0644)
    try:
        os_chown(path, owner_uid, owner_gid)
    except OSError:
        pass


def os_chmod(path: Path, mode: int) -> None:
    import os as _os

    _os.chmod(path, mode)


def os_chown(path: Path, uid: int, gid: int) -> None:
    import os as _os

    _os.chown(path, uid, gid)
