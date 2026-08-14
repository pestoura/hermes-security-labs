"""Repository-only tests for the CHG-HSL-057 operator live-observation harness.

Every test uses fakes/mocks only: no systemd query, no live socket, no
privileged identity, no payload, no persistent state. The live probe class is
never instantiated against a real socket.
"""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deployment" / "runtime-promotion" / "operator_live_observation_harness.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "chg_hsl_057_operator_harness", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


harness = _load()


class FakeServiceManager:
    """Fake service manager returning explicit PIDs per unit."""

    def __init__(self, mapping: dict[str, int]) -> None:
        self._mapping = mapping
        self.queried: list[str] = []

    def main_pid(self, unit: str) -> int:
        self.queried.append(unit)
        pid = self._mapping.get(unit, 0)
        if pid <= 0:
            raise harness.HarnessError("SERVICE_NOT_RUNNING", f"{unit} inactive")
        return pid


class FakeEntry:
    """Fake map entry mirroring the canonical NamespaceMapEntry attributes."""

    def __init__(self, inside: int, outside: int, length: int) -> None:
        self.inside_start = inside
        self.outside_start = outside
        self.length = length

    def as_dict(self) -> dict[str, int]:
        return {
            "inside_start": self.inside_start,
            "outside_start": self.outside_start,
            "length": self.length,
        }

    def __eq__(self, other: object) -> bool:
        return (
            getattr(other, "inside_start", None) == self.inside_start
            and getattr(other, "outside_start", None) == self.outside_start
            and getattr(other, "length", None) == self.length
        )

    def __hash__(self) -> int:
        return hash((self.inside_start, self.outside_start, self.length))


class FakeObservation:
    def __init__(self, pid: int, ticks: int, inode: int) -> None:
        self.pid = pid
        self.process_start_time_ticks = ticks
        self.user_namespace_inode = inode
        self.uid_map = (FakeEntry(0, 0, 4294967295),)
        self.gid_map = (FakeEntry(0, 0, 4294967295),)


class FakeObserver:
    """Fake procfs observer: fixed maps, no filesystem access."""

    def __init__(self, ticks: dict[int, int], inodes: dict[int, int]) -> None:
        self._ticks = ticks
        self._inodes = inodes

    def observe(self, pid: int) -> FakeObservation:
        if pid not in self._ticks:
            raise harness.HarnessError("PROCESS_UNAVAILABLE", f"pid {pid}")
        return FakeObservation(pid, self._ticks[pid], self._inodes[pid])


def _proc_root(tmp_path: Path, pids: dict[int, int]) -> Path:
    root = tmp_path / "proc"
    for pid, ticks in pids.items():
        directory = root / str(pid)
        directory.mkdir(parents=True)
        fields = ["0"] * 50
        # The canonical parser slices after ")" so index 0 is the state field.
        fields[0] = "S"
        fields[19] = str(ticks)
        (directory / "stat").write_text(
            f"{pid} (fake) " + " ".join(fields) + "\n", encoding="ascii"
        )
    return root


# ---------------------------------------------------------------------------
# Output directory boundary
# ---------------------------------------------------------------------------


def test_output_directory_must_be_absolute() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.resolve_output_directory("relative/evidence")
    assert excinfo.value.code == "OUTPUT_DIRECTORY_INVALID"


def test_output_directory_inside_repository_is_rejected() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.resolve_output_directory(str(ROOT / "deployment" / "evidence"))
    assert excinfo.value.code == "OUTPUT_DIRECTORY_INSIDE_REPOSITORY"


def test_output_directory_equal_to_repository_root_is_rejected() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.resolve_output_directory(str(ROOT))
    assert excinfo.value.code == "OUTPUT_DIRECTORY_INSIDE_REPOSITORY"


def test_output_directory_outside_repository_is_accepted(tmp_path: Path) -> None:
    resolved = harness.resolve_output_directory(str(tmp_path / "evidence"))
    assert resolved.is_absolute()


# ---------------------------------------------------------------------------
# PID discovery from the service manager only
# ---------------------------------------------------------------------------


def test_pids_come_from_service_manager_not_scanning(tmp_path: Path) -> None:
    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 222})
    identities = harness.discover_process_identities(
        manager=manager, proc_root=_proc_root(tmp_path, {111: 900, 222: 901})
    )
    assert manager.queried == [harness.GATEWAY_UNIT, harness.RUNNER_UNIT]
    assert identities["gateway"].pid == 111
    assert identities["runner"].start_time_ticks == 901


def test_inactive_unit_fails_closed(tmp_path: Path) -> None:
    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 0})
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.discover_process_identities(
            manager=manager, proc_root=_proc_root(tmp_path, {111: 900})
        )
    assert excinfo.value.code == "SERVICE_NOT_RUNNING"


def test_identical_pids_are_rejected(tmp_path: Path) -> None:
    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 111})
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.discover_process_identities(
            manager=manager, proc_root=_proc_root(tmp_path, {111: 900})
        )
    assert excinfo.value.code == "SERVICE_PID_COLLISION"


def test_missing_proc_entry_fails_closed(tmp_path: Path) -> None:
    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 222})
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.discover_process_identities(
            manager=manager, proc_root=_proc_root(tmp_path, {111: 900})
        )
    assert excinfo.value.code == "PROCESS_UNAVAILABLE"


def test_systemctl_argv_is_read_only_main_pid_query() -> None:
    captured: list[list[str]] = []

    def runner(command: list[str]) -> str:
        captured.append(list(command))
        return "4242\n"

    manager = harness.SystemctlServiceManager(runner=runner)
    if not harness.shutil.which("systemctl"):
        pytest.skip("systemctl is not present in this environment")
    assert manager.main_pid(harness.RUNNER_UNIT) == 4242
    argv = captured[0]
    assert argv[1:] == ["show", "-p", "MainPID", "--value", "--", harness.RUNNER_UNIT]
    for forbidden in ("start", "stop", "restart", "enable", "reload"):
        assert forbidden not in argv


# ---------------------------------------------------------------------------
# USER_NAMESPACE_MAPPING re-attestation
# ---------------------------------------------------------------------------


def _reattest(tmp_path: Path, *, inodes: dict[int, int], ticks: dict[int, int]):
    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 222})
    return harness.reattest_user_namespace_mapping(
        output_directory=tmp_path / "evidence",
        manager=manager,
        observer=FakeObserver(ticks, inodes),
        proc_root=_proc_root(tmp_path, ticks),
    )


def test_descriptor_is_generated_outside_git_with_runtime_pids(tmp_path: Path) -> None:
    result = _reattest(
        tmp_path, inodes={111: 4026531837, 222: 4026531837}, ticks={111: 900, 222: 901}
    )
    descriptor_path = Path(result.descriptor_path)
    assert descriptor_path.exists()
    assert ROOT.resolve() not in descriptor_path.resolve().parents
    document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    assert document["processes"]["gateway"]["pid"] == 111
    assert document["processes"]["runner"]["pid"] == 222
    assert document["runtime_status"] == "NOT_RUN"
    assert len(result.descriptor_sha256) == 64


def test_reattestation_binds_runtime_pids_and_starttimes(tmp_path: Path) -> None:
    result = _reattest(
        tmp_path, inodes={111: 4026531837, 222: 4026531837}, ticks={111: 900, 222: 901}
    )
    assert result.identities["gateway"]["start_time_ticks"] == 900
    assert result.identities["runner"]["start_time_ticks"] == 901
    assert result.re_attested is True


def test_reattestation_records_namespace_relationship(tmp_path: Path) -> None:
    same = _reattest(
        tmp_path / "a", inodes={111: 7, 222: 7}, ticks={111: 900, 222: 901}
    )
    different = _reattest(
        tmp_path / "b", inodes={111: 7, 222: 8}, ticks={111: 900, 222: 901}
    )
    assert same.observations["user_namespace_relationship"] == "same"
    assert different.observations["user_namespace_relationship"] == "different"


def test_reattestation_never_promotes(tmp_path: Path) -> None:
    payload = _reattest(
        tmp_path, inodes={111: 7, 222: 7}, ticks={111: 900, 222: 901}
    ).as_dict()
    assert payload["promotion_allowed"] is False
    assert payload["runtime_status"] == "NOT_RUN"


def test_rebound_pid_invalidates_reattestation(tmp_path: Path) -> None:
    """A PID whose start time differs from discovery time is fail-closed."""

    manager = FakeServiceManager({harness.GATEWAY_UNIT: 111, harness.RUNNER_UNIT: 222})
    # procfs reports 900/901 at discovery; the observer reports different ticks.
    result = harness.reattest_user_namespace_mapping(
        output_directory=tmp_path / "evidence",
        manager=manager,
        observer=FakeObserver({111: 950, 222: 901}, {111: 7, 222: 7}),
        proc_root=_proc_root(tmp_path, {111: 900, 222: 901}),
    )
    assert result.re_attested is False
    assert any("rebound" in finding for finding in result.findings)


# ---------------------------------------------------------------------------
# Ephemeral identity assumptions (no persistent credential)
# ---------------------------------------------------------------------------


def _which_setpriv(name: str) -> str | None:
    return "/usr/bin/setpriv" if name == "setpriv" else None


def test_root_probe_uid_is_rejected() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.plan_ephemeral_identity(unauthorized_uid=0, which=_which_setpriv)
    assert excinfo.value.code == "IDENTITY_ASSUMPTION_REJECTED"


@pytest.mark.parametrize("uid", sorted(harness.RESERVED_PROBE_UIDS))
def test_canonical_boundary_uids_are_rejected(uid: int) -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.plan_ephemeral_identity(unauthorized_uid=uid, which=_which_setpriv)
    assert excinfo.value.code == "IDENTITY_ASSUMPTION_REJECTED"


def test_authorized_uid_cannot_prove_a_negative() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.plan_ephemeral_identity(
            unauthorized_uid=6001, authorized_uids=(6001,), which=_which_setpriv
        )
    assert excinfo.value.code == "IDENTITY_ASSUMPTION_REJECTED"


def test_missing_identity_tool_fails_closed() -> None:
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.plan_ephemeral_identity(
            unauthorized_uid=6001, which=lambda _name: None
        )
    assert excinfo.value.code == "EPHEMERAL_IDENTITY_UNAVAILABLE"


def test_plan_uses_dispatch_gid_only_for_dac_reachability() -> None:
    plan = harness.plan_ephemeral_identity(
        unauthorized_uid=6001, which=_which_setpriv
    )
    assert plan.supplementary_gids == (harness.DISPATCH_GID,)
    assert plan.unauthorized_uid == 6001
    assert plan.as_dict()["creates_persistent_identity"] is False


def test_plan_argv_creates_no_user_or_group() -> None:
    plan = harness.plan_ephemeral_identity(
        unauthorized_uid=6001, which=_which_setpriv
    )
    argv = plan.argv(["/usr/bin/true"])
    assert "--reuid" in argv and "6001" in argv
    assert str(harness.DISPATCH_GID) in argv
    assert "--no-new-privs" in argv
    joined = " ".join(argv)
    for forbidden in ("useradd", "groupadd", "usermod", "gpasswd", "chown", "chmod"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# UNAUTHORIZED_PEER_NEGATIVE classification
# ---------------------------------------------------------------------------


class FakeStat:
    def __init__(self, *, mode: int, uid: int, gid: int, is_socket: bool = True) -> None:
        base = stat.S_IFSOCK if is_socket else stat.S_IFREG
        self.st_mode = base | mode
        self.st_uid = uid
        self.st_gid = gid


def _socket_stat(**kwargs: Any) -> Any:
    info = FakeStat(mode=0o660, uid=4101, gid=harness.DISPATCH_GID, **kwargs)
    return lambda _path: info


class FakeProbe:
    """Fake probe: returns a scripted observation and records send attempts."""

    def __init__(self, observation: dict[str, Any]) -> None:
        self._observation = observation
        self.sent: list[bytes] = []
        self.calls = 0

    def connect_and_observe(self, socket_path: str) -> dict[str, Any]:
        self.calls += 1
        return dict(self._observation)


def _observe(observation: dict[str, Any], **kwargs: Any):
    probe = FakeProbe(observation)
    result = harness.observe_unauthorized_peer_negative(
        unauthorized_uid=kwargs.pop("uid", 6001),
        probe=probe,
        which=_which_setpriv,
        stat_fn=_socket_stat(),
        **kwargs,
    )
    return result, probe


def test_hold_refusal_is_canonical_peer_negative_proof() -> None:
    result, probe = _observe(
        {
            "connected": True,
            "dac_blocked": False,
            "server_pid": 4242,
            "server_uid": 4101,
            "server_gid": harness.DISPATCH_GID,
            "closed_without_response": True,
        }
    )
    assert result.outcome == harness.PEER_HOLD_REFUSAL_OBSERVED
    assert result.canonical_proof is True
    assert result.peer_credentials["server_pid"] == 4242
    assert probe.sent == []
    assert result.payload_sent is False


def test_kernel_dac_eacces_is_not_canonical_proof() -> None:
    """A directory/socket DAC denial must NEVER count as peer-negative proof."""

    result, _probe = _observe({"connected": False, "dac_blocked": True, "errno": 13})
    assert result.outcome == harness.PEER_DAC_BLOCKED
    assert result.canonical_proof is False
    assert "NOT canonical" in result.detail


def test_connection_without_refusal_signal_is_not_proof() -> None:
    result, _probe = _observe(
        {
            "connected": True,
            "dac_blocked": False,
            "server_pid": 1,
            "server_uid": 4101,
            "server_gid": harness.DISPATCH_GID,
            "closed_without_response": False,
        }
    )
    assert result.outcome == harness.PEER_NO_REFUSAL_SIGNAL
    assert result.canonical_proof is False


def test_non_dac_connect_failure_is_not_proof() -> None:
    result, _probe = _observe({"connected": False, "dac_blocked": False, "errno": 111})
    assert result.outcome == harness.PEER_NO_REFUSAL_SIGNAL
    assert result.canonical_proof is False


def test_absent_socket_short_circuits_before_any_identity_use() -> None:
    probe = FakeProbe({"connected": True, "closed_without_response": True})

    def missing(_path: str) -> Any:
        raise FileNotFoundError(2, "missing")

    result = harness.observe_unauthorized_peer_negative(
        unauthorized_uid=6001, probe=probe, which=_which_setpriv, stat_fn=missing
    )
    assert result.outcome == harness.PEER_SOCKET_ABSENT
    assert result.canonical_proof is False
    assert probe.calls == 0


def test_non_socket_path_is_rejected() -> None:
    probe = FakeProbe({"connected": True, "closed_without_response": True})
    result = harness.observe_unauthorized_peer_negative(
        unauthorized_uid=6001,
        probe=probe,
        which=_which_setpriv,
        stat_fn=_socket_stat(is_socket=False),
    )
    assert result.outcome == harness.PEER_SOCKET_ABSENT
    assert probe.calls == 0


def test_rejected_identity_prevents_any_connection() -> None:
    probe = FakeProbe({"connected": True, "closed_without_response": True})
    result = harness.observe_unauthorized_peer_negative(
        unauthorized_uid=0, probe=probe, which=_which_setpriv, stat_fn=_socket_stat()
    )
    assert result.outcome == harness.PEER_ASSUMPTION_REJECTED
    assert probe.calls == 0


def test_missing_setpriv_prevents_any_connection() -> None:
    probe = FakeProbe({"connected": True, "closed_without_response": True})
    result = harness.observe_unauthorized_peer_negative(
        unauthorized_uid=6001,
        probe=probe,
        which=lambda _name: None,
        stat_fn=_socket_stat(),
    )
    assert result.outcome == harness.PEER_IDENTITY_UNAVAILABLE
    assert probe.calls == 0


def test_probe_source_never_sends_a_payload() -> None:
    """Static guarantee: the live probe contains no send/sendall/write call."""

    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (".sendall(", ".send(", ".sendmsg(", ".write("):
        assert forbidden not in source


def test_module_source_touches_no_docker_network_or_target() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "docker",
        "AF_INET",
        "requests",
        "urllib",
        "http.client",
        "useradd",
        "groupadd",
    ):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# Evidence envelope invariants
# ---------------------------------------------------------------------------


def _peer_proof() -> Any:
    result, _probe = _observe(
        {
            "connected": True,
            "dac_blocked": False,
            "server_pid": 4242,
            "server_uid": 4101,
            "server_gid": harness.DISPATCH_GID,
            "closed_without_response": True,
        }
    )
    return result


def test_envelope_is_always_fail_closed(tmp_path: Path) -> None:
    envelope = harness.compose_evidence(
        userns=_reattest(tmp_path, inodes={111: 7, 222: 7}, ticks={111: 900, 222: 901}),
        peer_negative=_peer_proof(),
    )
    assert envelope["promotion_allowed"] is False
    assert envelope["runtime_status"] == "NOT_RUN"
    assert envelope["campaign_state"] == "BLOCKED"
    assert envelope["promotion_recommendation"] == "HOLD"
    assert envelope["payload_sent"] is False
    assert envelope["persistent_state_created"] is False


def test_envelope_marks_uncollected_observations_not_run() -> None:
    envelope = harness.compose_evidence(userns=None, peer_negative=None)
    remaining = envelope["remaining_evidence"]
    assert "USER_NAMESPACE_MAPPING_NOT_RE_ATTESTED" in remaining
    assert "UNAUTHORIZED_PEER_NEGATIVE_NOT_PROVEN" in remaining
    for name in ("USER_NAMESPACE_MAPPING", "UNAUTHORIZED_PEER_NEGATIVE"):
        assert envelope["observations"][name]["runtime_status"] == "NOT_RUN"


def test_dac_block_keeps_peer_negative_unproven() -> None:
    result, _probe = _observe({"connected": False, "dac_blocked": True, "errno": 13})
    envelope = harness.compose_evidence(userns=None, peer_negative=result)
    assert "UNAUTHORIZED_PEER_NEGATIVE_NOT_PROVEN" in envelope["remaining_evidence"]


def test_envelope_never_claims_signer_or_trust() -> None:
    envelope = harness.compose_evidence(userns=None, peer_negative=_peer_proof())
    remaining = envelope["remaining_evidence"]
    assert "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED" in remaining
    assert "HOST_IDENTITY_SOCKET_TRUST_EVIDENCE_NOT_COMPOSED" in remaining
    assert "LIVE_RUNNER_EFFECT_NOT_RUN" in remaining


def test_evidence_is_written_outside_git_with_bound_hashes(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    envelope = harness.compose_evidence(userns=None, peer_negative=_peer_proof())
    path, digest = harness.write_evidence(envelope, output)
    assert ROOT.resolve() not in path.resolve().parents
    assert len(digest) == 64
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["promotion_allowed"] is False
    sidecar = (output / "operator-live-observation-evidence.json.sha256").read_text(
        encoding="utf-8"
    )
    assert digest in sidecar


def test_collect_writes_nothing_into_the_repository(tmp_path: Path) -> None:
    """Zero persistent repository state: evidence lands only in the output dir."""

    before = {p for p in (ROOT / "deployment" / "runtime-promotion").iterdir()}
    output = tmp_path / "evidence"
    harness.write_evidence(
        harness.compose_evidence(userns=None, peer_negative=None), output
    )
    after = {p for p in (ROOT / "deployment" / "runtime-promotion").iterdir()}
    assert before == after
    assert sorted(p.name for p in output.iterdir()) == [
        "operator-live-observation-evidence.json",
        "operator-live-observation-evidence.json.sha256",
    ]


def test_cli_plan_refuses_output_directory_inside_repository() -> None:
    code = harness.main(["--output-directory", str(ROOT / "x"), "plan"])
    assert code == 2


def test_cli_plan_requires_absolute_output_directory() -> None:
    assert harness.main(["--output-directory", "rel", "plan"]) == 2



