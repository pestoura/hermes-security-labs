#!/usr/bin/env python3
"""Deterministic fail-closed operator harness for the two remaining non-Vault
SAFE-LIVE observations of ``VAL-HSL-RUNNER-L1-LIVE-PROMOTION``.

Scope (exactly two observations, nothing else):

1. ``USER_NAMESPACE_MAPPING`` re-attestation of the CURRENT Gateway/Runner
   processes. PIDs are NEVER hardcoded and NEVER discovered by process scanning:
   they are resolved from the service manager (``systemctl show -p MainPID``)
   only at execution time, bound to the observed ``/proc/<pid>`` start time, and
   written into an explicit reviewed descriptor that is generated OUTSIDE the Git
   working tree. The canonical read-only observer
   ``runtime_userns_evidence.collect_userns_evidence`` performs the comparison.

2. ``UNAUTHORIZED_PEER_NEGATIVE`` against the LIVE Runner HOLD AF_UNIX socket.
   The probe runs under a TEMPORARY process identity that holds the
   ``hexor-dispatch`` supplementary GID solely so the socket is reachable at the
   DAC layer, while its UID is UNAUTHORIZED. The probe connects and observes the
   HOLD boundary refusing/closing. It NEVER sends a Runner request payload.

Hard invariants enforced by this module (fail-closed, no exceptions):

- No persistent state: no user, group, credential, trust store, policy, unit,
  socket, directory or file is created inside the repository or on the host
  outside the operator-specified output directory.
- No payload is ever written to the Runner socket (``send``/``sendall`` are never
  called), no Docker/network/target interaction, no policy enable, no trust
  binding, no signer selection.
- A kernel ``EACCES``/``EPERM`` at the directory or socket DAC layer is NOT
  accepted as peer-negative proof; it is recorded as
  ``DAC_BLOCKED_NOT_CANONICAL_PROOF`` and the observation stays ``NOT_RUN``.
- ``promotion_allowed`` is always ``False`` and ``runtime_status`` is always
  ``NOT_RUN``. This harness produces evidence; it never promotes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
USERNS_EVIDENCE_PATH = HERE / "runtime_userns_evidence.py"

# Canonical reviewed identity descriptor (a repository path, referenced by the
# generated descriptor; the generated descriptor itself lives outside Git).
DEFAULT_IDENTITY_DESCRIPTOR = (
    "deployment/runtime-promotion/templates/runner-identity-descriptor.example.yaml"
)

# Canonical service units and boundary identifiers (CHG-HSL-036 / #354 / #359).
GATEWAY_UNIT = "hexor-execution-gateway.service"
RUNNER_UNIT = "hexor-runner-dispatch.service"
RUNNER_HOLD_SOCKET = "/run/hexor/runner-dispatch.sock"
DISPATCH_GID = 4110

# Identities that must never be used as the "unauthorized" probe UID.
RESERVED_PROBE_UIDS = frozenset({0, 4100, 4101})

# Outcome codes for the peer-negative observation.
PEER_HOLD_REFUSAL_OBSERVED = "HOLD_REFUSAL_OBSERVED"
PEER_DAC_BLOCKED = "DAC_BLOCKED_NOT_CANONICAL_PROOF"
PEER_SOCKET_ABSENT = "SOCKET_ABSENT"
PEER_IDENTITY_UNAVAILABLE = "EPHEMERAL_IDENTITY_UNAVAILABLE"
PEER_ASSUMPTION_REJECTED = "IDENTITY_ASSUMPTION_REJECTED"
PEER_NO_REFUSAL_SIGNAL = "NO_REFUSAL_SIGNAL_OBSERVED"

REMAINING_EVIDENCE_ALWAYS = (
    "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED",
    "HOST_IDENTITY_SOCKET_TRUST_EVIDENCE_NOT_COMPOSED",
    "LIVE_RUNNER_EFFECT_NOT_RUN",
)


class HarnessError(ValueError):
    """Stable fail-closed harness error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise HarnessError("CANONICAL_MODULE_UNAVAILABLE", f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolve_output_directory(value: str | os.PathLike[str]) -> Path:
    """Validate the operator-specified output directory is OUTSIDE the Git tree.

    The harness refuses any relative path and any path inside the repository so
    generated descriptors and evidence can never be committed by accident.
    """

    candidate = Path(value)
    if not candidate.is_absolute():
        raise HarnessError(
            "OUTPUT_DIRECTORY_INVALID", "output directory must be an absolute path"
        )
    resolved = candidate.resolve()
    repo = ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise HarnessError(
            "OUTPUT_DIRECTORY_INSIDE_REPOSITORY",
            "output directory must be outside the Git working tree",
        )
    git_dir = (repo / ".git").resolve()
    if resolved == git_dir or git_dir in resolved.parents:
        raise HarnessError(
            "OUTPUT_DIRECTORY_INSIDE_REPOSITORY",
            "output directory must be outside the Git metadata directory",
        )
    return resolved


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Service-manager PID discovery (no process scanning, execution time only)
# ---------------------------------------------------------------------------


class ServiceManager(Protocol):
    """Minimal read-only service-manager query contract."""

    def main_pid(self, unit: str) -> int:
        ...


@dataclass(frozen=True)
class ProcessIdentity:
    """A runtime PID bound to its kernel start time (rebind-proof)."""

    unit: str
    pid: int
    start_time_ticks: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "pid": self.pid,
            "start_time_ticks": self.start_time_ticks,
        }


class SystemctlServiceManager:
    """Read-only ``systemctl show -p MainPID`` reader.

    Only the MainPID property of an explicit unit name is read. No unit is
    started, stopped, reloaded or enabled; no process list is scanned.
    """

    def __init__(self, *, runner: Any = None) -> None:
        self._runner = runner

    def main_pid(self, unit: str) -> int:
        binary = shutil.which("systemctl")
        if binary is None:
            raise HarnessError(
                "SERVICE_MANAGER_UNAVAILABLE", "systemctl is not available on PATH"
            )
        argv = [binary, "show", "-p", "MainPID", "--value", "--", unit]
        run = self._runner
        if run is None:  # pragma: no cover - exercised only on a live host
            import subprocess  # noqa: PLC0415 - deliberately lazy, read-only call

            def run(command: Sequence[str]) -> str:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    list(command),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if completed.returncode != 0:
                    raise HarnessError(
                        "SERVICE_MANAGER_QUERY_FAILED",
                        f"systemctl query failed for {unit}",
                    )
                return completed.stdout

        raw = run(argv)
        value = (raw or "").strip()
        if not value.isdecimal():
            raise HarnessError(
                "SERVICE_MAIN_PID_INVALID", f"{unit} did not report a numeric MainPID"
            )
        pid = int(value)
        if pid <= 0:
            raise HarnessError(
                "SERVICE_NOT_RUNNING", f"{unit} reports no active MainPID"
            )
        return pid


def _read_proc_start_ticks(pid: int, *, proc_root: Path = Path("/proc")) -> int:
    stat_path = proc_root / str(pid) / "stat"
    try:
        text = stat_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise HarnessError(
            "PROCESS_UNAVAILABLE", f"cannot read start time for PID {pid}"
        ) from exc
    closing = text.rfind(")")
    if closing < 0:
        raise HarnessError("PROC_STAT_INVALID", "proc stat lacks a command terminator")
    fields = text[closing + 1 :].strip().split()
    if len(fields) <= 19 or not fields[19].isdecimal():
        raise HarnessError("PROC_STAT_INVALID", "proc stat start time is unavailable")
    return int(fields[19])


def discover_process_identities(
    *,
    manager: ServiceManager | None = None,
    proc_root: Path = Path("/proc"),
    gateway_unit: str = GATEWAY_UNIT,
    runner_unit: str = RUNNER_UNIT,
) -> dict[str, ProcessIdentity]:
    """Resolve current Gateway/Runner PIDs from the service manager only."""

    service_manager = manager or SystemctlServiceManager()
    identities: dict[str, ProcessIdentity] = {}
    for role, unit in (("gateway", gateway_unit), ("runner", runner_unit)):
        pid = service_manager.main_pid(unit)
        identities[role] = ProcessIdentity(
            unit=unit,
            pid=pid,
            start_time_ticks=_read_proc_start_ticks(pid, proc_root=proc_root),
        )
    if identities["gateway"].pid == identities["runner"].pid:
        raise HarnessError(
            "SERVICE_PID_COLLISION",
            "gateway and runner resolved to the same MainPID",
        )
    return identities


# ---------------------------------------------------------------------------
# Observation 1: USER_NAMESPACE_MAPPING re-attestation
# ---------------------------------------------------------------------------


def _observed_maps(pid: int, *, observer: Any) -> tuple[list[dict[str, int]], list[dict[str, int]]]:
    observation = observer.observe(pid)
    uid_map = [entry.as_dict() for entry in observation.uid_map]
    gid_map = [entry.as_dict() for entry in observation.gid_map]
    return uid_map, gid_map


def build_reviewed_descriptor(
    identities: Mapping[str, ProcessIdentity],
    *,
    observer: Any,
    same_namespace: bool,
    identity_descriptor: str = DEFAULT_IDENTITY_DESCRIPTOR,
) -> dict[str, Any]:
    """Compose the explicit reviewed descriptor for the CURRENT runtime PIDs.

    The descriptor records the maps observed at this instant so the canonical
    observer re-attests them independently. It is data only; writing it is the
    caller's responsibility and always happens outside the Git tree.
    """

    processes: dict[str, Any] = {}
    for role in ("gateway", "runner"):
        identity = identities[role]
        uid_map, gid_map = _observed_maps(identity.pid, observer=observer)
        processes[role] = {
            "pid": identity.pid,
            "uid_map": uid_map,
            "gid_map": gid_map,
        }
    return {
        "schema_version": "1.0",
        "runtime_status": "NOT_RUN",
        "identity_descriptor": identity_descriptor,
        "user_namespace_relationship": "same" if same_namespace else "different",
        "processes": processes,
    }


def write_reviewed_descriptor(
    descriptor: Mapping[str, Any], output_directory: Path
) -> tuple[Path, str]:
    """Serialize the reviewed descriptor outside Git and return (path, sha256)."""

    output_directory.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(dict(descriptor), sort_keys=True)
    target = output_directory / "reviewed-userns-descriptor.generated.yaml"
    target.write_text(text, encoding="utf-8")
    return target, _sha256_text(text)


@dataclass(frozen=True)
class UserNamespaceReattestation:
    """Result of the USER_NAMESPACE_MAPPING re-attestation observation."""

    re_attested: bool
    descriptor_path: str
    descriptor_sha256: str
    identities: Mapping[str, Any]
    findings: tuple[str, ...]
    observations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation": "USER_NAMESPACE_MAPPING",
            "re_attested": self.re_attested,
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "descriptor_path": self.descriptor_path,
            "descriptor_sha256": self.descriptor_sha256,
            "runtime_identities": dict(self.identities),
            "findings": list(self.findings),
            "observations": dict(self.observations),
        }


def reattest_user_namespace_mapping(
    *,
    output_directory: Path,
    manager: ServiceManager | None = None,
    observer: Any = None,
    proc_root: Path = Path("/proc"),
    identity_descriptor: str = DEFAULT_IDENTITY_DESCRIPTOR,
) -> UserNamespaceReattestation:
    """Re-attest the current Gateway/Runner user-namespace mapping, read-only."""

    userns = _load_module("operator_harness_userns_evidence", USERNS_EVIDENCE_PATH)
    proc_observer = observer or userns.RealProcObserver()
    identities = discover_process_identities(
        manager=manager, proc_root=proc_root
    )

    gateway = proc_observer.observe(identities["gateway"].pid)
    runner = proc_observer.observe(identities["runner"].pid)
    same_namespace = gateway.user_namespace_inode == runner.user_namespace_inode

    descriptor = build_reviewed_descriptor(
        identities,
        observer=proc_observer,
        same_namespace=same_namespace,
        identity_descriptor=identity_descriptor,
    )
    descriptor_path, descriptor_sha = write_reviewed_descriptor(
        descriptor, output_directory
    )

    try:
        result = userns.collect_userns_evidence(descriptor, observer=proc_observer)
    except userns.UserNamespaceEvidenceError as exc:
        return UserNamespaceReattestation(
            re_attested=False,
            descriptor_path=str(descriptor_path),
            descriptor_sha256=descriptor_sha,
            identities={
                role: identity.as_dict() for role, identity in identities.items()
            },
            findings=(f"{exc.code}: {exc}",),
            observations={},
        )

    # Bind the runtime start times: a PID that was rebound between discovery and
    # observation invalidates the re-attestation (fail-closed).
    findings = list(result.findings)
    for role in ("gateway", "runner"):
        observed = gateway if role == "gateway" else runner
        if observed.process_start_time_ticks != identities[role].start_time_ticks:
            findings.append(f"{role} PID was rebound during observation")

    return UserNamespaceReattestation(
        re_attested=not findings and result.user_namespace_checks_passed,
        descriptor_path=str(descriptor_path),
        descriptor_sha256=descriptor_sha,
        identities={role: identity.as_dict() for role, identity in identities.items()},
        findings=tuple(findings),
        observations=result.observations,
    )


# ---------------------------------------------------------------------------
# Observation 2: UNAUTHORIZED_PEER_NEGATIVE against the live HOLD socket
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EphemeralIdentityPlan:
    """A validated plan for a temporary, non-persistent process identity.

    ``setpriv``/``runuser`` only *assume* an identity for the lifetime of one
    process; neither creates a user or a group. The plan is validated fail-closed
    before use: the UID must be unauthorized, the supplementary GID must be the
    canonical dispatch GID (DAC reachability only), and no persistent change may
    be implied.
    """

    tool: str
    tool_path: str
    unauthorized_uid: int
    primary_gid: int
    supplementary_gids: tuple[int, ...]

    def argv(self, command: Sequence[str]) -> list[str]:
        groups = ",".join(str(gid) for gid in self.supplementary_gids)
        if self.tool == "setpriv":
            return [
                self.tool_path,
                "--reuid",
                str(self.unauthorized_uid),
                "--regid",
                str(self.primary_gid),
                "--groups",
                groups,
                "--no-new-privs",
                "--",
                *command,
            ]
        raise HarnessError(
            "EPHEMERAL_TOOL_UNSUPPORTED", f"unsupported identity tool {self.tool}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "unauthorized_uid": self.unauthorized_uid,
            "primary_gid": self.primary_gid,
            "supplementary_gids": list(self.supplementary_gids),
            "creates_persistent_identity": False,
        }


def plan_ephemeral_identity(
    *,
    unauthorized_uid: int,
    dispatch_gid: int = DISPATCH_GID,
    authorized_uids: Sequence[int] = (),
    which: Any = shutil.which,
) -> EphemeralIdentityPlan:
    """Validate assumptions for the temporary identity, fail-closed.

    Rejects a UID that is privileged, canonical (gateway/runner) or listed as
    authorized, and requires an ephemeral-identity tool to actually exist.
    """

    if unauthorized_uid in RESERVED_PROBE_UIDS:
        raise HarnessError(
            "IDENTITY_ASSUMPTION_REJECTED",
            "probe UID must not be root or a canonical boundary identity",
        )
    if unauthorized_uid <= 0:
        raise HarnessError(
            "IDENTITY_ASSUMPTION_REJECTED", "probe UID must be a positive non-root UID"
        )
    if unauthorized_uid in set(authorized_uids):
        raise HarnessError(
            "IDENTITY_ASSUMPTION_REJECTED",
            "probe UID is authorized and cannot prove a negative",
        )
    tool_path = which("setpriv")
    if not tool_path:
        raise HarnessError(
            "EPHEMERAL_IDENTITY_UNAVAILABLE",
            "no ephemeral identity tool (setpriv) is available",
        )
    return EphemeralIdentityPlan(
        tool="setpriv",
        tool_path=str(tool_path),
        unauthorized_uid=unauthorized_uid,
        primary_gid=unauthorized_uid,
        supplementary_gids=(dispatch_gid,),
    )


def inspect_hold_socket(
    socket_path: str = RUNNER_HOLD_SOCKET, *, stat_fn: Any = os.stat
) -> dict[str, Any]:
    """Read-only stat of the HOLD socket (no connect, no payload)."""

    try:
        info = stat_fn(socket_path)
    except OSError as exc:
        return {
            "path": socket_path,
            "present": False,
            "error": type(exc).__name__,
        }
    return {
        "path": socket_path,
        "present": True,
        "is_socket": stat.S_ISSOCK(info.st_mode),
        "mode": stat.S_IMODE(info.st_mode) & 0o7777,
        "uid": info.st_uid,
        "gid": info.st_gid,
    }


@dataclass(frozen=True)
class PeerNegativeResult:
    """Result of the UNAUTHORIZED_PEER_NEGATIVE observation."""

    outcome: str
    canonical_proof: bool
    socket: Mapping[str, Any]
    identity_plan: Mapping[str, Any] | None
    peer_credentials: Mapping[str, Any] | None
    detail: str
    payload_sent: bool = False

    def as_dict(self) -> dict[str, Any]:
        # payload_sent must be provably False for every code path.
        assert self.payload_sent is False  # noqa: S101 - invariant guard
        return {
            "observation": "UNAUTHORIZED_PEER_NEGATIVE",
            "outcome": self.outcome,
            "canonical_proof": self.canonical_proof,
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "payload_sent": False,
            "socket": dict(self.socket),
            "identity_plan": dict(self.identity_plan) if self.identity_plan else None,
            "peer_credentials": (
                dict(self.peer_credentials) if self.peer_credentials else None
            ),
            "detail": self.detail,
        }


class PeerProbe(Protocol):
    """Injectable connect/observe contract (never sends a payload)."""

    def connect_and_observe(self, socket_path: str) -> dict[str, Any]:
        ...


class LiveHoldSocketProbe:
    """Connect to the live HOLD socket and observe refusal/close, no payload.

    The probe NEVER calls ``send``/``sendall``. It connects, reads the kernel
    ``SO_PEERCRED`` of the accepting server (proving a real peer relationship),
    then observes whether the HOLD boundary refuses/closes without accepting a
    request. A connect that fails with ``EACCES``/``EPERM`` is a DAC block, not a
    canonical peer-negative proof.
    """

    def connect_and_observe(self, socket_path: str) -> dict[str, Any]:  # pragma: no cover - live only
        import errno  # noqa: PLC0415

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            try:
                sock.connect(socket_path)
            except PermissionError as exc:
                return {"connected": False, "dac_blocked": True, "errno": exc.errno}
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EPERM}:
                    return {"connected": False, "dac_blocked": True, "errno": exc.errno}
                return {"connected": False, "dac_blocked": False, "errno": exc.errno}
            # Read the server's kernel credentials (our own side observes theirs).
            import struct  # noqa: PLC0415

            raw = sock.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            pid, uid, gid = struct.unpack("3i", raw)
            # Observe HOLD behavior WITHOUT sending: a HOLD boundary that refuses
            # closes the connection; recv returns b"" (EOF) or the peer resets.
            closed = False
            try:
                data = sock.recv(1)
                closed = data == b""
            except OSError:
                closed = True
            return {
                "connected": True,
                "dac_blocked": False,
                "server_pid": pid,
                "server_uid": uid,
                "server_gid": gid,
                "closed_without_response": closed,
            }
        finally:
            sock.close()


def observe_unauthorized_peer_negative(
    *,
    unauthorized_uid: int,
    socket_path: str = RUNNER_HOLD_SOCKET,
    dispatch_gid: int = DISPATCH_GID,
    authorized_uids: Sequence[int] = (),
    probe: PeerProbe | None = None,
    which: Any = shutil.which,
    stat_fn: Any = os.stat,
) -> PeerNegativeResult:
    """Observe HOLD refusal of an unauthorized (SO_PEERCRED) identity."""

    socket_info = inspect_hold_socket(socket_path, stat_fn=stat_fn)
    if not socket_info.get("present") or not socket_info.get("is_socket"):
        return PeerNegativeResult(
            outcome=PEER_SOCKET_ABSENT,
            canonical_proof=False,
            socket=socket_info,
            identity_plan=None,
            peer_credentials=None,
            detail="HOLD socket is absent or not a socket; observation NOT_RUN",
        )

    try:
        plan = plan_ephemeral_identity(
            unauthorized_uid=unauthorized_uid,
            dispatch_gid=dispatch_gid,
            authorized_uids=authorized_uids,
            which=which,
        )
    except HarnessError as exc:
        outcome = (
            PEER_IDENTITY_UNAVAILABLE
            if exc.code == "EPHEMERAL_IDENTITY_UNAVAILABLE"
            else PEER_ASSUMPTION_REJECTED
        )
        return PeerNegativeResult(
            outcome=outcome,
            canonical_proof=False,
            socket=socket_info,
            identity_plan=None,
            peer_credentials=None,
            detail=f"{exc.code}: {exc}",
        )

    observation = (probe or LiveHoldSocketProbe()).connect_and_observe(socket_path)

    if observation.get("dac_blocked"):
        return PeerNegativeResult(
            outcome=PEER_DAC_BLOCKED,
            canonical_proof=False,
            socket=socket_info,
            identity_plan=plan.as_dict(),
            peer_credentials=None,
            detail=(
                "connection refused at directory/socket DAC (EACCES/EPERM); "
                "kernel DAC block is NOT canonical peer-negative proof"
            ),
        )
    if not observation.get("connected"):
        return PeerNegativeResult(
            outcome=PEER_NO_REFUSAL_SIGNAL,
            canonical_proof=False,
            socket=socket_info,
            identity_plan=plan.as_dict(),
            peer_credentials=None,
            detail=(
                "connection did not establish for a non-DAC reason; "
                "no SO_PEERCRED-derived refusal observed"
            ),
        )

    peer_credentials = {
        "server_pid": observation.get("server_pid"),
        "server_uid": observation.get("server_uid"),
        "server_gid": observation.get("server_gid"),
    }
    if observation.get("closed_without_response"):
        return PeerNegativeResult(
            outcome=PEER_HOLD_REFUSAL_OBSERVED,
            canonical_proof=True,
            socket=socket_info,
            identity_plan=plan.as_dict(),
            peer_credentials=peer_credentials,
            detail=(
                "peer connected under an unauthorized UID (dispatch GID for DAC "
                "reachability only); HOLD boundary refused/closed without "
                "accepting a request and no payload was sent"
            ),
        )
    return PeerNegativeResult(
        outcome=PEER_NO_REFUSAL_SIGNAL,
        canonical_proof=False,
        socket=socket_info,
        identity_plan=plan.as_dict(),
        peer_credentials=peer_credentials,
        detail=(
            "connection established but HOLD refusal/close was not observed; "
            "observation NOT_RUN (fail-closed)"
        ),
    )


# ---------------------------------------------------------------------------
# Machine-readable evidence envelope (written outside Git only)
# ---------------------------------------------------------------------------


def compose_evidence(
    *,
    userns: UserNamespaceReattestation | None,
    peer_negative: PeerNegativeResult | None,
) -> dict[str, Any]:
    """Compose the fail-closed evidence envelope.

    ``promotion_allowed`` is hardcoded ``False`` and ``runtime_status`` hardcoded
    ``NOT_RUN``: this envelope is evidence for a HOLD campaign, never a promotion
    signal. An observation that was not collected is emitted as ``NOT_RUN``.
    """

    remaining: list[str] = list(REMAINING_EVIDENCE_ALWAYS)
    if userns is None or not userns.re_attested:
        remaining.append("USER_NAMESPACE_MAPPING_NOT_RE_ATTESTED")
    if peer_negative is None or not peer_negative.canonical_proof:
        remaining.append("UNAUTHORIZED_PEER_NEGATIVE_NOT_PROVEN")

    return {
        "schema_version": "1.0",
        "harness": "operator_live_observation_harness",
        "campaign": "VAL-HSL-RUNNER-L1-LIVE-PROMOTION",
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "campaign_state": "BLOCKED",
        "promotion_recommendation": "HOLD",
        "payload_sent": False,
        "persistent_state_created": False,
        "observations": {
            "USER_NAMESPACE_MAPPING": (
                userns.as_dict()
                if userns is not None
                else {"observation": "USER_NAMESPACE_MAPPING", "runtime_status": "NOT_RUN"}
            ),
            "UNAUTHORIZED_PEER_NEGATIVE": (
                peer_negative.as_dict()
                if peer_negative is not None
                else {
                    "observation": "UNAUTHORIZED_PEER_NEGATIVE",
                    "runtime_status": "NOT_RUN",
                }
            ),
        },
        "remaining_evidence": sorted(set(remaining)),
    }


def write_evidence(envelope: Mapping[str, Any], output_directory: Path) -> tuple[Path, str]:
    """Write the evidence envelope (canonical JSON) plus its own digest."""

    output_directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(envelope), sort_keys=True, indent=2) + "\n"
    digest = _sha256_text(text)
    target = output_directory / "operator-live-observation-evidence.json"
    target.write_text(text, encoding="utf-8")
    (output_directory / "operator-live-observation-evidence.json.sha256").write_text(
        f"{digest}  {target.name}\n", encoding="utf-8"
    )
    return target, digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output-directory",
        required=True,
        help="absolute operator-specified directory OUTSIDE the Git working tree",
    )
    parser.add_argument("--socket-path", default=RUNNER_HOLD_SOCKET)
    parser.add_argument("--dispatch-gid", type=int, default=DISPATCH_GID)
    parser.add_argument(
        "--unauthorized-uid",
        type=int,
        default=None,
        help="temporary unauthorized UID for the peer-negative probe",
    )
    parser.add_argument(
        "command",
        choices=("plan", "collect"),
        help="plan = validate assumptions only; collect = observe read-only",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        output_directory = resolve_output_directory(args.output_directory)
    except HarnessError as exc:
        print(json.dumps({"code": exc.code, "error": str(exc)}, sort_keys=True))
        return 2

    if args.command == "plan":
        plan_payload: dict[str, Any] = {
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "output_directory": str(output_directory),
            "socket": inspect_hold_socket(args.socket_path),
            "units": {"gateway": GATEWAY_UNIT, "runner": RUNNER_UNIT},
        }
        if args.unauthorized_uid is not None:
            try:
                plan_payload["identity_plan"] = plan_ephemeral_identity(
                    unauthorized_uid=args.unauthorized_uid,
                    dispatch_gid=args.dispatch_gid,
                ).as_dict()
            except HarnessError as exc:
                plan_payload["identity_plan"] = {"code": exc.code, "error": str(exc)}
        print(json.dumps(plan_payload, sort_keys=True, indent=2))
        return 0

    userns_result: UserNamespaceReattestation | None = None
    peer_result: PeerNegativeResult | None = None
    errors: list[dict[str, str]] = []
    try:
        userns_result = reattest_user_namespace_mapping(
            output_directory=output_directory
        )
    except HarnessError as exc:
        errors.append({"observation": "USER_NAMESPACE_MAPPING", "code": exc.code})

    if args.unauthorized_uid is not None:
        peer_result = observe_unauthorized_peer_negative(
            unauthorized_uid=args.unauthorized_uid,
            socket_path=args.socket_path,
            dispatch_gid=args.dispatch_gid,
        )

    envelope = compose_evidence(userns=userns_result, peer_negative=peer_result)
    if errors:
        envelope["errors"] = errors
    path, digest = write_evidence(envelope, output_directory)
    print(json.dumps({"evidence": str(path), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





