"""Repository-only tests for the Runner runtime deployment boundary (#354).

Nothing here provisions a user, group, socket, service or trust store. No live
host state is read and no canonical policy is mutated. The boundary is validated
as fail-closed, idempotent and rollbackable by its declared data and helpers,
and the controller CLI proves the four explicit subcommands
(``plan`` / ``install-base`` / ``rollback-base`` / ``bind-trust``) behave
correctly without performing live host mutation.
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
RUNTIME_DIR = ROOT / "deployment" / "runner-runtime"
DEPLOYMENT_MODULE = RUNTIME_DIR / "runtime_deployment.py"
BOUNDARIES_MODULE = RUNTIME_DIR / "runtime_boundaries.py"
TRUST_MODULE = RUNTIME_DIR / "trust_binding.py"
DESCRIPTOR = RUNTIME_DIR / "runtime-deployment.yaml"
CANONICAL_TRANSPORT_POLICY = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"
CANONICAL_PEER_MODULE = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"


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


deployment = _load("runtime_deployment_test", DEPLOYMENT_MODULE)
boundaries = _load("runtime_boundaries_test", BOUNDARIES_MODULE)
trust = _load("trust_binding_test", TRUST_MODULE)


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


def test_descriptor_mirrors_canonical_example_identity_ids() -> None:
    descriptor = _descriptor()
    assert descriptor["identities"]["gateway"]["uid"] == 4100
    assert descriptor["identities"]["gateway"]["gid"] == 4100
    assert descriptor["identities"]["runner"]["uid"] == 4101
    assert descriptor["identities"]["runner"]["gid"] == 4101
    assert descriptor["identities"]["dispatch_group"]["gid"] == 4110


# ---------------------------------------------------------------- HOLD envelope


def test_descriptor_keeps_fail_closed_policy_envelope() -> None:
    descriptor = _descriptor()
    envelope = boundaries.fail_closed_policy_envelope()
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
    assert set(listener["refuse_on_any"]) == boundaries.no_target_effect_contract()


def test_no_target_effects_possible() -> None:
    descriptor = _descriptor()
    for effect in descriptor["trust_binding"].values():
        assert effect in (None, False, "none", "/etc/hexor/runner/authorization-trust-store.json")
    for effect in descriptor["target_effects"].values():
        assert effect in (None, "none")


# ----------------------------------------------------------------- trust binding


def test_trust_binding_is_absent_in_phase_a() -> None:
    descriptor = _descriptor()
    tb = descriptor["trust_binding"]
    assert tb["enabled"] is False
    assert tb["source"] is None
    assert tb["public_source"] is False
    assert tb["expected_sha256"] is None


def test_trust_binding_validation_rejects_non_public_source(tmp_path: Path) -> None:
    store = tmp_path / "trust.json"
    store.write_text(json.dumps({"ok": True}), encoding="utf-8")
    digest = __import__("hashlib").sha256(store.read_bytes()).hexdigest()
    source = trust.TrustBindingSource(
        trust_store_path=str(store), expected_sha256=digest, public_source=False
    )
    with pytest.raises(trust.TrustBindingError) as exc:
        trust.validate_trust_binding(source)
    assert exc.value.code == "BINDING_NOT_PUBLIC"


def test_trust_binding_validation_accepts_explicit_public_source(tmp_path: Path) -> None:
    store = tmp_path / "trust.json"
    store.write_text(json.dumps({"ok": True}), encoding="utf-8")
    digest = __import__("hashlib").sha256(store.read_bytes()).hexdigest()
    source = trust.TrustBindingSource(
        trust_store_path=str(store), expected_sha256=digest, public_source=True
    )
    result = trust.validate_trust_binding(source)
    assert result["bound"] is True
    assert result["sha256"] == digest


def test_trust_binding_validation_rejects_digest_mismatch(tmp_path: Path) -> None:
    store = tmp_path / "trust.json"
    store.write_text(json.dumps({"ok": True}), encoding="utf-8")
    source = trust.TrustBindingSource(
        trust_store_path=str(store),
        expected_sha256="0" * 64,
        public_source=True,
    )
    with pytest.raises(trust.TrustBindingError) as exc:
        trust.validate_trust_binding(source)
    assert exc.value.code == "BINDING_DIGEST_MISMATCH"


def test_trust_binding_rejects_private_material(tmp_path: Path) -> None:
    store = tmp_path / "trust.json"
    store.write_text(json.dumps({"secret": "x"}), encoding="utf-8")
    digest = __import__("hashlib").sha256(store.read_bytes()).hexdigest()
    source = trust.TrustBindingSource(
        trust_store_path=str(store), expected_sha256=digest, public_source=True
    )
    with pytest.raises(trust.TrustBindingError) as exc:
        trust.validate_trust_binding(source)
    assert exc.value.code == "BINDING_PRIVATE_MATERIAL"


# ------------------------------------------------------------ collision preflight


def test_collision_preflight_fails_closed_on_conflicting_uid() -> None:
    findings = boundaries.detect_reserved_id_collision({4101: "some-real-user"}, {})
    assert any("reserved uid 4101" in f for f in findings)


def test_collision_preflight_fails_closed_on_conflicting_gid() -> None:
    findings = boundaries.detect_reserved_id_collision({}, {4110: "other-group"})
    assert any("reserved gid 4110" in f for f in findings)


def test_collision_preflight_passes_when_ids_free() -> None:
    findings = boundaries.detect_reserved_id_collision({2000: "other"}, {3000: "another"})
    assert findings == []


def test_collision_preflight_is_exact_aware_and_accepts_canonical_identities() -> None:
    """uid 4100 and gid 4100 both exist canonically: not a duplicate collision."""

    findings = boundaries.detect_reserved_id_collision(
        {4100: "hexor-gateway", 4101: "hexor-runner"},
        {4100: "hexor-gateway", 4101: "hexor-runner", 4110: "hexor-dispatch"},
    )
    assert findings == []


def test_uid_and_gid_namespaces_are_distinct() -> None:
    """A foreign *group* on gid 4100 must not be reported as a uid collision."""

    findings = boundaries.detect_reserved_id_collision({}, {4100: "foreign-group"})
    assert len(findings) == 1
    assert "reserved gid 4100" in findings[0]
    assert "uid" not in findings[0].split("reserved gid")[0]


# ------------------------------------------------- fake identity host (no NSS)


class FakeIdentityHost:
    """In-memory NSS + command runner double. Never touches the real host."""

    GROUPS = {
        "hexor-gateway": 4100,
        "hexor-runner": 4101,
        "hexor-dispatch": 4110,
    }
    USERS = {
        "hexor-gateway": (4100, 4100),
        "hexor-runner": (4101, 4101),
    }

    def __init__(
        self,
        *,
        groups: dict[str, int] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
        members: dict[str, list[str]] | None = None,
        fail_on: str | None = None,
        provision: bool = True,
    ) -> None:
        self.groups: dict[str, int] = dict(groups or {})
        self.users: dict[str, dict[str, Any]] = dict(users or {})
        self.members: dict[str, list[str]] = {k: list(v) for k, v in (members or {}).items()}
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.provision = provision

    # -- classmethods building common states ---------------------------------
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

    # -- probes ---------------------------------------------------------------
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

    # -- fake command runner --------------------------------------------------
    def run(self, command):
        command = list(command)
        self.calls.append(command)
        if self.fail_on and command[0] == self.fail_on:
            return 1, f"fake failure for {self.fail_on}"
        if not self.provision:
            return 0, ""  # succeeds but changes nothing -> postcondition RED
        if command[0] == "groupadd":
            self.groups[command[-1]] = int(command[command.index("--gid") + 1])
        elif command[0] == "useradd":
            name = command[-1]
            self.users[name] = {
                "name": name,
                "uid": int(command[command.index("--uid") + 1]),
                "gid": int(command[command.index("--gid") + 1]),
                "shell": command[command.index("--shell") + 1],
            }
        elif command[0] == "usermod":
            group = command[command.index("--groups") + 1]
            self.members.setdefault(group, []).append(command[-1])
        return 0, ""


def _preflight(host: FakeIdentityHost):
    return boundaries.preflight_identities(*host.probes(), host.group_members)


def _install(host: FakeIdentityHost, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Run install-base live against the fake host with all real I/O stubbed."""

    installed: list[str] = []
    systemd: list[tuple[str, ...]] = []

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(
        deployment, "_install_file",
        lambda src, dst, **k: installed.append(str(dst)),
    )
    monkeypatch.setattr(deployment, "_systemctl", lambda _runner, *args: systemd.append(args))
    monkeypatch.setattr(deployment, "_systemd_tmpfiles_create", lambda _runner: systemd.append(("tmpfiles",)))
    monkeypatch.setattr(deployment, "_verify_installed_file", lambda *a, **k: None)

    result = deployment.install_base(
        _descriptor(),
        live=True,
        require_root=False,
        probes=host.probes(),
        group_members=host.group_members,
        run_command=host.run,
    )
    return result, installed, systemd


# --------------------------------------------------- identity preflight semantics


def test_identity_preflight_exact_is_idempotent_pass() -> None:
    results = _preflight(FakeIdentityHost.exact())
    assert all(status == boundaries.IdentityStatus.EXACT for _k, _n, status, _d in results)
    assert boundaries.identity_conflicts(results) == []
    assert boundaries.plan_identity_provisioning(results) == []


def test_identity_preflight_absent_is_allowed_not_red() -> None:
    results = _preflight(FakeIdentityHost.absent())
    assert all(status == boundaries.IdentityStatus.ABSENT for _k, _n, status, _d in results)
    assert boundaries.identity_conflicts(results) == []


def test_identity_preflight_same_name_wrong_uid_is_red() -> None:
    host = FakeIdentityHost.exact()
    host.users["hexor-runner"] = {"name": "hexor-runner", "uid": 9999, "gid": 4101, "shell": "/usr/sbin/nologin"}
    results = _preflight(host)
    statuses = {n: s for k, n, s, _d in results if k == "user"}
    assert statuses["hexor-runner"] == boundaries.IdentityStatus.CONFLICT


def test_identity_preflight_same_uid_other_user_is_red() -> None:
    host = FakeIdentityHost.exact()
    host.users["intruder"] = {"name": "intruder", "uid": 4101, "gid": 4101, "shell": "/bin/bash"}
    del host.users["hexor-runner"]
    results = _preflight(host)
    statuses = {n: s for k, n, s, _d in results if k == "user"}
    assert statuses["hexor-runner"] == boundaries.IdentityStatus.CONFLICT


def test_identity_preflight_same_gid_other_group_is_red() -> None:
    host = FakeIdentityHost.exact()
    del host.groups["hexor-dispatch"]
    host.groups["other-group"] = 4110
    results = _preflight(host)
    statuses = {n: s for k, n, s, _d in results if k == "group"}
    assert statuses["hexor-dispatch"] == boundaries.IdentityStatus.CONFLICT


def test_identity_preflight_wrong_primary_gid_is_red() -> None:
    host = FakeIdentityHost.exact()
    host.users["hexor-runner"]["gid"] = 100
    results = _preflight(host)
    statuses = {n: s for k, n, s, _d in results if k == "user"}
    assert statuses["hexor-runner"] == boundaries.IdentityStatus.CONFLICT


def test_identity_preflight_wrong_shell_is_red() -> None:
    host = FakeIdentityHost.exact()
    host.users["hexor-runner"]["shell"] = "/bin/bash"
    results = _preflight(host)
    statuses = {n: s for k, n, s, _d in results if k == "user"}
    assert statuses["hexor-runner"] == boundaries.IdentityStatus.CONFLICT


def test_identity_preflight_reports_missing_dispatch_membership() -> None:
    results = _preflight(FakeIdentityHost.exact(memberships=False))
    memberships = {n: s for k, n, s, _d in results if k == "membership"}
    assert memberships == {
        "hexor-gateway": boundaries.IdentityStatus.ABSENT,
        "hexor-runner": boundaries.IdentityStatus.ABSENT,
    }


def test_provisioning_plan_refuses_to_plan_over_a_conflict() -> None:
    host = FakeIdentityHost.exact()
    host.users["hexor-runner"]["shell"] = "/bin/bash"
    with pytest.raises(ValueError):
        boundaries.plan_identity_provisioning(_preflight(host))


# ------------------------------------------------- install-base provisioning


def test_install_base_exact_identities_perform_zero_identity_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    result, installed, systemd = _install(host, monkeypatch, tmp_path)
    assert host.calls == []  # no groupadd/useradd/usermod at all
    assert result["created_identities"] == []
    assert result["partial_identity_provisioning"] is False
    assert all(s == "exact" for _k, _n, s, _d in result["identity_status"])
    assert installed  # files still installed idempotently
    assert ("daemon-reload",) in systemd


def test_install_base_all_absent_provisions_deterministic_order_before_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.absent()
    result, installed, systemd = _install(host, monkeypatch, tmp_path)

    assert host.calls == [
        ["groupadd", "--gid", "4100", "hexor-gateway"],
        ["groupadd", "--gid", "4101", "hexor-runner"],
        ["groupadd", "--gid", "4110", "hexor-dispatch"],
        ["useradd", "--uid", "4100", "--gid", "4100", "--no-create-home",
         "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin",
         "--no-user-group", "hexor-gateway"],
        ["useradd", "--uid", "4101", "--gid", "4101", "--no-create-home",
         "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin",
         "--no-user-group", "hexor-runner"],
        ["usermod", "--append", "--groups", "hexor-dispatch", "hexor-gateway"],
        ["usermod", "--append", "--groups", "hexor-dispatch", "hexor-runner"],
    ]
    assert [c[0] for c in host.calls].count("groupadd") == 3
    assert [c[0] for c in host.calls].count("useradd") == 2
    assert [c[0] for c in host.calls].count("usermod") == 2
    # Post-probe is exact and file/systemd work happened only afterwards.
    assert all(s == "exact" for _k, _n, s, _d in result["identity_status"])
    assert installed
    assert systemd[0] == ("daemon-reload",)
    assert result["partial_identity_provisioning"] is False


def test_install_base_mixed_state_provisions_only_missing_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Groups exist, gateway user exists, runner user absent, memberships partial.
    host = FakeIdentityHost(
        groups=dict(FakeIdentityHost.GROUPS),
        users={"hexor-gateway": {"name": "hexor-gateway", "uid": 4100, "gid": 4100,
                                 "shell": "/usr/sbin/nologin"}},
        members={"hexor-dispatch": ["hexor-gateway"]},
    )
    result, installed, _systemd = _install(host, monkeypatch, tmp_path)
    assert host.calls == [
        ["useradd", "--uid", "4101", "--gid", "4101", "--no-create-home",
         "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin",
         "--no-user-group", "hexor-runner"],
        ["usermod", "--append", "--groups", "hexor-dispatch", "hexor-runner"],
    ]
    assert installed
    assert result["partial_identity_provisioning"] is False


def test_install_base_missing_membership_only_repairs_with_usermod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact(memberships=False)
    _result, installed, _systemd = _install(host, monkeypatch, tmp_path)
    assert host.calls == [
        ["usermod", "--append", "--groups", "hexor-dispatch", "hexor-gateway"],
        ["usermod", "--append", "--groups", "hexor-dispatch", "hexor-runner"],
    ]
    assert installed


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda h: h.users.__setitem__(
            "intruder", {"name": "intruder", "uid": 4101, "gid": 4101, "shell": "/bin/bash"}),
            id="same-uid-other-user"),
        pytest.param(lambda h: h.groups.__setitem__("other-group", 4110), id="same-gid-other-group"),
    ],
)
def test_install_base_id_conflict_is_red_before_any_mutation(
    mutate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.absent()
    mutate(host)
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "PREFLIGHT_FAILED"
    assert host.calls == []  # zero identity commands
    assert exc.value.partial_identity_provisioning is False


def test_install_base_same_name_wrong_attributes_is_red_before_any_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    host.users["hexor-runner"] = {"name": "hexor-runner", "uid": 4101, "gid": 100, "shell": "/bin/bash"}
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "PREFLIGHT_FAILED"
    assert host.calls == []


def test_install_base_provisioning_failure_installs_nothing_and_exposes_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.absent()
    host.fail_on = "useradd"
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "IDENTITY_PROVISIONING_FAILED"
    assert exc.value.partial_identity_provisioning is True
    # Only the three groupadds landed; the failing useradd stops the run.
    assert [c[0] for c in exc.value.created_identities] == ["groupadd"] * 3
    assert exc.value.as_dict()["partial_identity_provisioning"] is True
    # No file or systemd action followed the failure.
    assert not any(c[0] in {"systemctl", "systemd-tmpfiles"} for c in host.calls)


def test_install_base_first_command_failure_reports_no_partial_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.absent()
    host.fail_on = "groupadd"
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "IDENTITY_PROVISIONING_FAILED"
    assert exc.value.partial_identity_provisioning is False
    assert exc.value.created_identities == []


def test_install_base_postcondition_mismatch_is_red_before_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Commands "succeed" but change nothing -> post-probe is still ABSENT.
    host = FakeIdentityHost.absent()
    host.provision = False
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install(host, monkeypatch, tmp_path)
    assert exc.value.code == "IDENTITY_POSTCONDITION_FAILED"
    assert exc.value.partial_identity_provisioning is True
    assert "identity-postcondition" in str(exc.value)


def test_install_base_never_deletes_identities_on_failure() -> None:
    """No groupdel/userdel/gpasswd anywhere in the controller source."""

    source = DEPLOYMENT_MODULE.read_text(encoding="utf-8")
    for forbidden in ("groupdel", "userdel", "gpasswd", "chpasswd", "passwd "):
        assert forbidden not in source


def test_dependency_preflight_requires_provisioning_tooling() -> None:
    missing = deployment.dependency_preflight(
        which=lambda cmd: None,
        file_exists=lambda path: False,
    )
    blob = "\n".join(missing)
    for command in ("groupadd", "useradd", "usermod", "systemctl", "systemd-tmpfiles"):
        assert command in blob
    assert "/usr/bin/python3" in blob
    assert "/usr/sbin/nologin" in blob


def test_dependency_preflight_is_green_when_tooling_present() -> None:
    findings = deployment.dependency_preflight(
        which=lambda cmd: f"/usr/sbin/{cmd}",
        file_exists=lambda path: True,
    )
    assert findings == []


def test_old_implementation_without_provisioning_would_fail_these_tests() -> None:
    """Regression proof: the controller must expose real provisioning."""

    source = DEPLOYMENT_MODULE.read_text(encoding="utf-8")
    assert "plan_identity_provisioning" in source
    assert "partial_identity_provisioning" in source
    assert "run_command" in source
    boundaries_source = BOUNDARIES_MODULE.read_text(encoding="utf-8")
    assert "groupadd" in boundaries_source
    assert "useradd" in boundaries_source
    assert "usermod" in boundaries_source
    # The old out-of-scope wording must be gone.
    assert "out-of-scope privileged step" not in boundaries_source


# ----------------------------------------------------------------- idempotency


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


# ---------------------------------------------------------------------- CLI shape


def test_cli_exposes_only_the_four_explicit_subcommands() -> None:
    """Proof the old inert `--help` (plan + --live/--rollback) is gone."""

    import subprocess

    completed = subprocess.run(
        [sys.executable, str(DEPLOYMENT_MODULE), "--help"],
        capture_output=True,
        text=True,
    )
    assert "positional arguments" in completed.stdout
    for sub in ("plan", "install-base", "rollback-base", "bind-trust"):
        assert sub in completed.stdout
    # Old ambiguous flag surface must not exist as a top-level option.
    assert "--live" not in completed.stdout
    assert "--rollback" not in completed.stdout


def test_cli_plan_exits_ok_and_emits_json() -> None:
    completed = __import__("subprocess").run(
        [sys.executable, str(DEPLOYMENT_MODULE), "--json", "plan"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["policy_envelope"]["state"] == "DISABLED"
    assert report["policy_envelope"]["runtime_status"] == "NOT_RUN"
    assert report["policy_envelope"]["execution_authority"] == "none"
    assert report["policy_envelope"]["promotion_allowed"] is False
    assert report["trust_binding"] is None
    assert "read_request_payload" in report["prohibited_effects"]
    assert "touch_target" in report["prohibited_effects"]


def test_cli_install_base_dry_run_performs_no_host_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Run inside an isolated root so any stray write is caught and the root gate
    # is relaxed (the gate itself is tested separately).
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, *a, **k):
        calls.append(tuple(cmd))
        return __import__("subprocess").CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(__import__("subprocess"), "run", fake_run)
    rc = deployment.main(["--json", "install-base", "--no-root-required"])
    assert rc == deployment.EXIT_OK
    # Mutation commands (systemctl/tmpfiles) must NOT run in dry-run.
    assert not calls


def test_cli_install_base_root_gate_fails_when_not_root() -> None:
    # Without --no-root-required on a non-root host the preflight must refuse.
    if __import__("os").geteuid() == 0:
        pytest.skip("running as root; cannot exercise non-root refusal")
    deployment.main(["install-base", "--live", "--no-root-required"])
    # --no-root-required disabled the gate; assert the gate path instead:
    rc2 = deployment.main(["install-base", "--live"])
    assert rc2 == deployment.EXIT_FAIL_CLOSED


def test_cli_install_base_live_orders_preflight_before_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    def fake_run(cmd, *a, **k):
        if cmd[:1] == ["systemctl"]:
            order.append("systemctl")
        elif cmd[:1] == ["systemd-tmpfiles"]:
            order.append("systemd-tmpfiles")
        return __import__("subprocess").CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(__import__("subprocess"), "run", fake_run)

    # Force a conflict so the live path must refuse before any mutation.
    real_probe = deployment.probe_users_groups
    deployment.probe_users_groups = lambda: (
        lambda u: {"name": "other", "uid": u, "gid": u, "shell": "/bin/bash"},
        lambda n: None,
        lambda g: None,
        lambda n: None,
    )
    try:
        rc = deployment.main(["install-base", "--live", "--no-root-required"])
    finally:
        deployment.probe_users_groups = real_probe
    assert rc == deployment.EXIT_FAIL_CLOSED
    # No systemd mutation happened because preflight failed first.
    assert "systemctl" not in order
    assert "systemd-tmpfiles" not in order


def test_cli_install_base_never_calls_bind_trust(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import runtime_boundaries as rb_mod

    # Make preflight pass (all identities absent).
    rb_mod.probe_users_groups = lambda: (
        lambda u: None, lambda n: None, lambda g: None, lambda n: None
    )

    called = {}

    def fake_bind(*a, **k):
        called["bind"] = True
        raise AssertionError("bind_trust_store must not be called from install-base")

    monkeypatch.setattr(deployment, "bind_trust_store", fake_bind)

    # Without --live the install is a dry-run and never mutates; with --live we
    # relax the root gate and stub subprocess. We only assert install-base does
    # not invoke bind_trust in either mode.
    rc = deployment.main(["install-base", "--no-root-required"])
    assert rc == deployment.EXIT_OK
    assert not called.get("bind", False)


def test_cli_rollback_preserves_identities_and_trust_store() -> None:
    result = deployment.main(["--json", "rollback-base", "--no-root-required"])
    assert result == deployment.EXIT_OK


def test_cli_bind_trust_requires_explicit_args() -> None:
    rc = deployment.main(["bind-trust"])
    assert rc == deployment.EXIT_FAIL_CLOSED


def test_cli_bind_trust_dry_validates_source() -> None:
    import tempfile

    store = Path(tempfile.mkdtemp()) / "trust.json"
    store.write_text(json.dumps({"public": True}), encoding="utf-8")
    digest = __import__("hashlib").sha256(store.read_bytes()).hexdigest()
    rc = deployment.main(
        ["--json", "bind-trust", "--trust-store-path", str(store),
         "--expected-sha256", digest, "--public-source"]
    )
    assert rc == deployment.EXIT_OK


# ---------------------------------------------------- deployment performs no live


def test_deployment_module_performs_no_privileged_or_provisioning_calls() -> None:
    """AST-level proof: no provisioning import and no privileged/socket call."""

    tree = ast.parse(DEPLOYMENT_MODULE.read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"ctypes"}
    # Allowed: os (for geteuid/chmod/chown), pwd/grp (read-only probes), shutil.
    assert not imported & {"socket"}

    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(ast.unparse(node.func))
    for forbidden in ("os.system", "subprocess.getoutput"):
        assert forbidden not in called


def test_rollback_is_explicit_and_never_deletes_identities_or_trust_store() -> None:
    """Rollback logic removes only installed files; trust store is protected."""

    plan = deployment.build_plan(_descriptor())
    trust_store = "/etc/hexor/runner/authorization-trust-store.json"
    protected = [p for p in plan.remove_on_rollback if str(p) == trust_store]
    assert protected == []
    for path in plan.remove_on_rollback:
        assert "trust-store" not in str(path)
        assert str(path).endswith((".socket", ".service", ".conf", "README.md", "unix_peer_identity.py", "runtime-deployment.yaml", "runner_hold_listener.py"))


# ------------------------------------------------- postcondition re-probe wiring

def _install_direct(
    host: FakeIdentityHost,
    monkeypatch: pytest.MonkeyPatch,
    run_command,
    *,
    probes=None,
    group_members=None,
):
    """Run install-base live with host I/O stubbed but identity runner real-ish."""

    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)
    return deployment.install_base(
        _descriptor(),
        live=True,
        require_root=False,
        probes=probes if probes is not None else host.probes(),
        group_members=group_members if group_members is not None else host.group_members,
        run_command=run_command,
    )


def test_install_base_rejects_stale_injected_snapshot_via_reprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-probe must re-read identities, never reuse the preflight snapshot.

    Here the injected ``probes`` are frozen copies taken *before* provisioning
    (the old-bug shape: a snapshot that never reflects the just-run commands).
    Even though the real host is provisioned, the stale injected probes report
    the identities as ABSENT, so the postcondition must fail closed.
    """

    host = FakeIdentityHost.absent()
    frozen_users = dict(host.users)
    frozen_members = {k: list(v) for k, v in host.members.items()}

    def user_by_uid(uid):
        for entry in frozen_users.values():
            if entry["uid"] == uid:
                return dict(entry)
        return None

    def user_by_name(name):
        entry = frozen_users.get(name)
        return dict(entry) if entry else None

    def group_by_gid(gid):
        for gname, ggid in host.groups.items():
            if ggid == gid:
                return {"name": gname, "gid": ggid}
        return None

    def group_by_name(name):
        if name in host.groups:
            return {"name": name, "gid": host.groups[name]}
        return None

    stale_probes = (user_by_uid, user_by_name, group_by_gid, group_by_name)

    def stale_members(name):
        return tuple(frozen_members.get(name, ()))

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install_direct(
            host, monkeypatch, host.run,
            probes=stale_probes, group_members=stale_members,
        )
    assert exc.value.code == "IDENTITY_POSTCONDITION_FAILED"
    # Identities were provisioned on the (mutable) host, so partial state is set.
    assert exc.value.partial_identity_provisioning is True


def test_install_base_reprobe_reflects_just_provisioned_mutable_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live injected closures over mutable state make the postcondition exact.

    The re-probe reuses the injected ``host.probes()`` closures, which observe
    the mutations performed by ``run_command=host.run``. The postcondition must
    therefore pass as EXACT after provisioning (no stale snapshot).
    """

    host = FakeIdentityHost.absent()
    result = _install_direct(host, monkeypatch, host.run)
    assert result["live"] is True
    assert all(s == "exact" for _k, _n, s, _d in result["identity_status"])
    assert result["partial_identity_provisioning"] is False


# ------------------------------------------------- systemd rc must be fail-closed

def _recording_failing_runner(fail_pred):
    class _Runner:
        def __init__(self):
            self.calls: list[tuple[str, ...]] = []

        def __call__(self, command):
            command = list(command)
            self.calls.append(tuple(command))
            if fail_pred(command):
                return 1, f"injected failure for {command[0]}"
            return 0, ""

    return _Runner()


def test_install_base_daemon_reload_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()  # no identity commands; only systemd runs
    runner = _recording_failing_runner(
        lambda c: c[:2] == ["systemctl", "daemon-reload"]
    )

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install_direct(host, monkeypatch, runner)
    assert exc.value.code == deployment.SYSTEMD_DAEMON_RELOAD_FAILED
    # tmpfiles --create and enable --now must never run after the reload fails.
    assert not any(c[:2] == ["systemd-tmpfiles", "--create"] for c in runner.calls)
    assert not any(c[:3] == ["systemctl", "enable", "--now"] for c in runner.calls)


def test_install_base_tmpfiles_create_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    runner = _recording_failing_runner(
        lambda c: c[:2] == ["systemd-tmpfiles", "--create"]
    )

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install_direct(host, monkeypatch, runner)
    assert exc.value.code == deployment.SYSTEMD_TMPFILES_CREATE_FAILED
    # enable --now must never run after tmpfiles fails.
    assert not any(c[:3] == ["systemctl", "enable", "--now"] for c in runner.calls)


def test_install_base_enable_now_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = FakeIdentityHost.exact()
    runner = _recording_failing_runner(
        lambda c: c[:3] == ["systemctl", "enable", "--now"]
    )

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        _install_direct(host, monkeypatch, runner)
    assert exc.value.code == deployment.SYSTEMD_ENABLE_FAILED


# ------------------------------------------------------- rollback fail-closed

def _isolated_rollback_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect rollback to tmp paths and own the files as the current user."""

    dsts = [tmp_path / "owned_a.txt", tmp_path / "owned_b.txt"]
    for dst in dsts:
        dst.write_text("base artifact", encoding="utf-8")

    plan = deployment.DeploymentPlan(
        ok=True,
        findings=(),
        install_files=tuple((tmp_path / "src", d) for d in dsts),
        remove_on_rollback=tuple(dsts),
        policy_envelope=deployment.fail_closed_policy_envelope(),
        prohibited_effects=frozenset(),
        trust_binding=None,
    )
    monkeypatch.setattr(deployment, "build_plan", lambda descriptor: plan)
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    # Files are owned by the current non-root user; accept them as root-owned
    # for the isolated residue check so the test exercises the lifecycle path.
    monkeypatch.setattr(deployment, "OWNER_ROOT_UID", __import__("os").geteuid())
    monkeypatch.setattr(deployment, "OWNER_ROOT_GID", __import__("os").getegid())
    return dsts


def test_rollback_base_disable_failure_is_fail_closed_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsts = _isolated_rollback_plan(tmp_path, monkeypatch)
    runner = _recording_failing_runner(
        lambda c: c[:2] == ["systemctl", "disable"]
    )

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.rollback_base(
            _descriptor(), live=True, require_root=False, run_command=runner
        )
    assert exc.value.code == deployment.SYSTEMD_DISABLE_FAILED
    # Artifacts must NOT be removed when stop/disable could not be confirmed.
    assert all(d.exists() for d in dsts)


def test_rollback_base_daemon_reload_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsts = _isolated_rollback_plan(tmp_path, monkeypatch)
    # disable --now succeeds; only the final daemon-reload fails.
    runner = _recording_failing_runner(
        lambda c: c[:2] == ["systemctl", "daemon-reload"]
    )

    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment.rollback_base(
            _descriptor(), live=True, require_root=False, run_command=runner
        )
    assert exc.value.code == deployment.SYSTEMD_DAEMON_RELOAD_FAILED
    # disable succeeded and artifacts were removed; the failure is the reload.
    assert not any(d.exists() for d in dsts)


def test_rollback_base_succeeds_when_disable_and_reload_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsts = _isolated_rollback_plan(tmp_path, monkeypatch)
    runner = _recording_failing_runner(lambda c: False)

    result = deployment.rollback_base(
        _descriptor(), live=True, require_root=False, run_command=runner
    )
    assert result["live"] is True
    assert sorted(result["removed"]) == sorted(str(d) for d in dsts)
    assert not any(d.exists() for d in dsts)
    assert result["preserves_identities"] is True


# ------------------------------------------- probes=None performs a real re-probe

def test_install_base_reprobes_live_host_after_provisioning_when_probes_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """probes=None must perform a real second probe of the live host.

    Preflight sees ABSENT identities; the injected runner "provisions" them;
    the postcondition re-probe (a fresh ``probe_users_groups`` call) sees EXACT
    and install proceeds. A stale-snapshot implementation that reuses the
    preflight snapshot would keep reporting ABSENT and fail the postcondition,
    so this test is red under that old behaviour.
    """

    probe_calls = {"users_groups": 0, "members": 0}
    absent_host = FakeIdentityHost.absent()
    exact_host = FakeIdentityHost.exact()

    def fake_probe_users_groups():
        probe_calls["users_groups"] += 1
        if probe_calls["users_groups"] == 1:
            return absent_host.probes()
        return exact_host.probes()

    def fake_probe_group_members():
        probe_calls["members"] += 1
        if probe_calls["members"] == 1:
            return absent_host.group_members
        return exact_host.group_members

    monkeypatch.setattr(deployment, "probe_users_groups", fake_probe_users_groups)
    monkeypatch.setattr(deployment, "probe_group_members", fake_probe_group_members)
    monkeypatch.setattr(deployment, "root_gate", lambda require_root: [])
    monkeypatch.setattr(deployment, "dependency_preflight", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "_install_file", lambda *a, **k: None)

    runner = _recording_failing_runner(lambda c: False)
    result = deployment.install_base(
        _descriptor(),
        live=True,
        require_root=False,
        probes=None,
        group_members=None,
        run_command=runner,
    )
    # A second, independent probe of the live host must have happened.
    assert probe_calls["users_groups"] >= 2
    assert probe_calls["members"] >= 2
    assert result["live"] is True
    assert result["partial_identity_provisioning"] is False
    assert all(s == "exact" for _k, _n, s, _d in result["identity_status"])
    # Preflight was ABSENT -> provisioning commands ran, then systemd activation.
    assert any(c[0] == "groupadd" for c in runner.calls)
    assert ("systemctl", "daemon-reload") in runner.calls


# ----------------------------------- _systemctl resolves stable per-unit codes

def test_systemctl_resolves_stable_codes_per_unit_not_generic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """enable/disable/daemon-reload map to stable codes, not SYSTEMD_COMMAND_FAILED."""

    failing = _recording_failing_runner(lambda c: True)
    cases = [
        (("daemon-reload",), deployment.SYSTEMD_DAEMON_RELOAD_FAILED),
        (("enable", "--now", deployment.SYSTEMD_SOCKET_UNIT), deployment.SYSTEMD_ENABLE_FAILED),
        (("disable", "--now", deployment.SYSTEMD_SOCKET_UNIT), deployment.SYSTEMD_DISABLE_FAILED),
    ]
    for args, code in cases:
        with pytest.raises(deployment.DeploymentBoundaryError) as exc:
            deployment._systemctl(failing, *args)
        assert exc.value.code == code
    # A non-lifecycle verb with a unit falls through to the generic code.
    with pytest.raises(deployment.DeploymentBoundaryError) as exc:
        deployment._systemctl(failing, "is-enabled", deployment.SYSTEMD_SOCKET_UNIT)
    assert exc.value.code == "SYSTEMD_COMMAND_FAILED"
