#!/usr/bin/env python3
"""Read-only user-namespace mapping evidence for explicit Runner process PIDs.

The observer reads only kernel-owned procfs metadata for the two explicitly
reviewed process IDs in the descriptor. It performs no process discovery,
namespace entry, privilege change, mutation, networking or target interaction.

A PASS proves only that the observed UID/GID maps and user-namespace relation
match the reviewed descriptor at observation time. It never grants promotion.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
SCHEMA_PATH = HERE / "runtime-userns-evidence-descriptor.schema.json"
DEFAULT_DESCRIPTOR = HERE / "templates" / "runtime-userns-evidence-descriptor.example.yaml"
IDENTITY_PREFLIGHT_PATH = HERE / "runner_identity_preflight.py"
MAX_PROC_BYTES = 16 * 1024
MAX_ID = 2**32

REMAINING_EVIDENCE = (
    "HOST_IDENTITY_SOCKET_TRUST_EVIDENCE_NOT_COMPOSED",
    "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED",
    "UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN",
    "LIVE_AUDIT_SINK_NOT_OBSERVED",
    "LIVE_RUNNER_EFFECT_NOT_RUN",
)


class UserNamespaceEvidenceError(ValueError):
    """Stable fail-closed error for user-namespace observation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NamespaceMapEntry:
    inside_start: int
    outside_start: int
    length: int

    def as_dict(self) -> dict[str, int]:
        return {
            "inside_start": self.inside_start,
            "outside_start": self.outside_start,
            "length": self.length,
        }


@dataclass(frozen=True)
class ProcessNamespaceObservation:
    pid: int
    process_start_time_ticks: int
    user_namespace_inode: int
    uid_map: tuple[NamespaceMapEntry, ...]
    gid_map: tuple[NamespaceMapEntry, ...]


class NamespaceObserver(Protocol):
    def observe(self, pid: int) -> ProcessNamespaceObservation:
        ...


@dataclass(frozen=True)
class UserNamespaceEvidenceResult:
    user_namespace_checks_passed: bool
    promotion_allowed: bool
    runtime_status: str
    findings: tuple[str, ...]
    remaining_evidence: tuple[str, ...]
    observations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_namespace_checks_passed": self.user_namespace_checks_passed,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
            "findings": list(self.findings),
            "remaining_evidence": list(self.remaining_evidence),
            "observations": dict(self.observations),
        }


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identity_preflight = _load_module(
    "runtime_userns_identity_preflight", IDENTITY_PREFLIGHT_PATH
)


def _safe_descriptor_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise UserNamespaceEvidenceError(
            "IDENTITY_DESCRIPTOR_PATH_INVALID",
            "identity descriptor reference must be relative",
        )
    relative = Path(value)
    if "." in relative.parts or ".." in relative.parts:
        raise UserNamespaceEvidenceError(
            "IDENTITY_DESCRIPTOR_PATH_INVALID",
            "identity descriptor reference cannot contain dot traversal",
        )
    resolved = (ROOT / relative).resolve()
    try:
        resolved.relative_to(HERE.resolve())
    except ValueError as exc:
        raise UserNamespaceEvidenceError(
            "IDENTITY_DESCRIPTOR_PATH_INVALID",
            "identity descriptor must remain under deployment/runtime-promotion",
        ) from exc
    return resolved


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise UserNamespaceEvidenceError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise UserNamespaceEvidenceError(code, f"{path.name} must contain an object")
    return value


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise UserNamespaceEvidenceError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise UserNamespaceEvidenceError(code, f"{path.name} must contain an object")
    return value


def _entry(value: Mapping[str, Any]) -> NamespaceMapEntry:
    return NamespaceMapEntry(
        inside_start=int(value["inside_start"]),
        outside_start=int(value["outside_start"]),
        length=int(value["length"]),
    )


def _entries(value: Sequence[Mapping[str, Any]]) -> tuple[NamespaceMapEntry, ...]:
    return tuple(_entry(item) for item in value)


def _range_end(start: int, length: int) -> int:
    end = start + length
    if end > MAX_ID:
        raise UserNamespaceEvidenceError(
            "NAMESPACE_MAP_INVALID",
            "namespace mapping range exceeds 32-bit identifier space",
        )
    return end


def _validate_map(entries: tuple[NamespaceMapEntry, ...], label: str) -> None:
    inside_ranges: list[tuple[int, int]] = []
    outside_ranges: list[tuple[int, int]] = []
    for entry in entries:
        inside_end = _range_end(entry.inside_start, entry.length)
        outside_end = _range_end(entry.outside_start, entry.length)
        inside_ranges.append((entry.inside_start, inside_end))
        outside_ranges.append((entry.outside_start, outside_end))

    for ranges, dimension in ((inside_ranges, "inside"), (outside_ranges, "outside")):
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1]:
                raise UserNamespaceEvidenceError(
                    "NAMESPACE_MAP_INVALID",
                    f"{label} has overlapping {dimension} ranges",
                )


def _covers_outside(entries: tuple[NamespaceMapEntry, ...], identifier: int) -> bool:
    return any(
        entry.outside_start <= identifier < entry.outside_start + entry.length
        for entry in entries
    )


def _validate_descriptor(document: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH, "DESCRIPTOR_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise UserNamespaceEvidenceError(
            "DESCRIPTOR_INVALID", f"{location}: {first.message}"
        )

    _safe_descriptor_path(document["identity_descriptor"])
    processes = document["processes"]
    if processes["gateway"]["pid"] == processes["runner"]["pid"]:
        raise UserNamespaceEvidenceError(
            "DESCRIPTOR_INVALID", "gateway and runner must use distinct explicit PIDs"
        )
    for role in ("gateway", "runner"):
        for map_name in ("uid_map", "gid_map"):
            _validate_map(_entries(processes[role][map_name]), f"{role}.{map_name}")


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    document = _load_yaml(path, "DESCRIPTOR_UNREADABLE")
    _validate_descriptor(document)
    return document


def _parse_proc_map(text: str, label: str) -> tuple[NamespaceMapEntry, ...]:
    entries: list[NamespaceMapEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split()
        if len(fields) != 3 or not all(field.isdecimal() for field in fields):
            raise UserNamespaceEvidenceError(
                "PROC_MAP_INVALID", f"{label} contains a malformed mapping line"
            )
        entry = NamespaceMapEntry(*(int(field) for field in fields))
        if entry.length < 1:
            raise UserNamespaceEvidenceError(
                "PROC_MAP_INVALID", f"{label} contains a zero-length mapping"
            )
        entries.append(entry)
    if not 1 <= len(entries) <= 5:
        raise UserNamespaceEvidenceError(
            "PROC_MAP_INVALID", f"{label} must contain between one and five mappings"
        )
    _validate_map(tuple(entries), label)
    return tuple(entries)


def _parse_start_time(stat_text: str) -> int:
    closing = stat_text.rfind(")")
    if closing < 0:
        raise UserNamespaceEvidenceError(
            "PROC_STAT_INVALID", "proc stat record lacks a command terminator"
        )
    fields = stat_text[closing + 1 :].strip().split()
    # The slice starts at field 3 (state); starttime is field 22 => index 19.
    if len(fields) <= 19 or not fields[19].isdecimal():
        raise UserNamespaceEvidenceError(
            "PROC_STAT_INVALID", "proc stat start time is unavailable"
        )
    return int(fields[19])


class RealProcObserver:
    """Linux procfs observer using explicit PID directory file descriptors only."""

    @staticmethod
    def _flags(*, directory: bool = False) -> int:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        return flags

    @staticmethod
    def _read_at(directory_fd: int, name: str) -> str:
        try:
            fd = os.open(name, RealProcObserver._flags(), dir_fd=directory_fd)
        except OSError as exc:
            raise UserNamespaceEvidenceError(
                "PROC_READ_FAILED", f"cannot open procfs field {name}"
            ) from exc
        try:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PROC_BYTES:
                    raise UserNamespaceEvidenceError(
                        "PROC_READ_REFUSED", f"procfs field {name} exceeds safe read limit"
                    )
                chunks.append(chunk)
        except OSError as exc:
            raise UserNamespaceEvidenceError(
                "PROC_READ_FAILED", f"cannot read procfs field {name}"
            ) from exc
        finally:
            os.close(fd)
        try:
            return b"".join(chunks).decode("ascii")
        except UnicodeDecodeError as exc:
            raise UserNamespaceEvidenceError(
                "PROC_READ_FAILED", f"procfs field {name} is not ASCII"
            ) from exc

    def observe(self, pid: int) -> ProcessNamespaceObservation:
        proc_path = f"/proc/{pid}"
        try:
            directory_fd = os.open(proc_path, self._flags(directory=True))
        except OSError as exc:
            raise UserNamespaceEvidenceError(
                "PROCESS_UNAVAILABLE", f"explicit process PID {pid} is unavailable"
            ) from exc
        try:
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                raise UserNamespaceEvidenceError(
                    "PROCESS_UNAVAILABLE", "explicit procfs PID path is not a directory"
                )
            before = _parse_start_time(self._read_at(directory_fd, "stat"))
            uid_map = _parse_proc_map(
                self._read_at(directory_fd, "uid_map"), f"pid {pid} uid_map"
            )
            gid_map = _parse_proc_map(
                self._read_at(directory_fd, "gid_map"), f"pid {pid} gid_map"
            )
            try:
                user_ns_inode = os.stat(
                    "ns/user", dir_fd=directory_fd, follow_symlinks=True
                ).st_ino
            except OSError as exc:
                raise UserNamespaceEvidenceError(
                    "USER_NAMESPACE_UNAVAILABLE",
                    f"user namespace metadata is unavailable for PID {pid}",
                ) from exc
            after = _parse_start_time(self._read_at(directory_fd, "stat"))
            if before != after:
                raise UserNamespaceEvidenceError(
                    "PROCESS_IDENTITY_CHANGED",
                    f"PID {pid} changed identity during observation",
                )
            return ProcessNamespaceObservation(
                pid=pid,
                process_start_time_ticks=before,
                user_namespace_inode=int(user_ns_inode),
                uid_map=uid_map,
                gid_map=gid_map,
            )
        finally:
            os.close(directory_fd)


def _safe_observation(value: ProcessNamespaceObservation) -> dict[str, Any]:
    return {
        "pid": value.pid,
        "process_start_time_ticks": value.process_start_time_ticks,
        "user_namespace_inode": value.user_namespace_inode,
        "uid_map": [entry.as_dict() for entry in value.uid_map],
        "gid_map": [entry.as_dict() for entry in value.gid_map],
    }


def collect_userns_evidence(
    descriptor: Mapping[str, Any],
    *,
    observer: NamespaceObserver | None = None,
) -> UserNamespaceEvidenceResult:
    _validate_descriptor(descriptor)
    identity_path = _safe_descriptor_path(descriptor["identity_descriptor"])
    try:
        identity_document = identity_preflight.load_descriptor(identity_path)
        identity_result = identity_preflight.run_preflight(identity_document)
    except Exception as exc:  # noqa: BLE001 - normalize canonical preflight errors
        raise UserNamespaceEvidenceError(
            "IDENTITY_DESCRIPTOR_INVALID", "canonical identity descriptor cannot be validated"
        ) from exc
    if not identity_result.ok:
        raise UserNamespaceEvidenceError(
            "IDENTITY_DESCRIPTOR_INVALID", "; ".join(identity_result.findings)
        )

    proc = observer or RealProcObserver()
    findings: list[str] = []
    observations: dict[str, Any] = {}
    observed_by_role: dict[str, ProcessNamespaceObservation] = {}

    for role in ("gateway", "runner"):
        expectation = descriptor["processes"][role]
        identity = identity_document["identities"][role]
        expected_uid_map = _entries(expectation["uid_map"])
        expected_gid_map = _entries(expectation["gid_map"])
        host_uid = int(identity["uid"])
        host_gid = int(identity["gid"])

        if not _covers_outside(expected_uid_map, host_uid):
            findings.append(
                f"{role} expected uid_map does not cover declared host UID {host_uid}"
            )
        if not _covers_outside(expected_gid_map, host_gid):
            findings.append(
                f"{role} expected gid_map does not cover declared host GID {host_gid}"
            )

        observed = proc.observe(int(expectation["pid"]))
        observed_by_role[role] = observed
        if observed.uid_map != expected_uid_map:
            findings.append(f"{role} uid_map differs from reviewed expectation")
        if observed.gid_map != expected_gid_map:
            findings.append(f"{role} gid_map differs from reviewed expectation")

        safe = _safe_observation(observed)
        safe["declared_host_uid_covered"] = _covers_outside(observed.uid_map, host_uid)
        safe["declared_host_gid_covered"] = _covers_outside(observed.gid_map, host_gid)
        if not safe["declared_host_uid_covered"]:
            findings.append(f"{role} observed uid_map does not cover declared host UID")
        if not safe["declared_host_gid_covered"]:
            findings.append(f"{role} observed gid_map does not cover declared host GID")
        observations[role] = safe

    same_namespace = (
        observed_by_role["gateway"].user_namespace_inode
        == observed_by_role["runner"].user_namespace_inode
    )
    expected_same = descriptor["user_namespace_relationship"] == "same"
    if same_namespace != expected_same:
        findings.append(
            "gateway/runner user-namespace relationship differs from reviewed expectation"
        )
    observations["user_namespace_relationship"] = (
        "same" if same_namespace else "different"
    )

    return UserNamespaceEvidenceResult(
        user_namespace_checks_passed=not findings,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
        findings=tuple(findings),
        remaining_evidence=REMAINING_EVIDENCE,
        observations=observations,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        descriptor = load_descriptor(args.descriptor)
        result = collect_userns_evidence(descriptor)
    except UserNamespaceEvidenceError as exc:
        payload = {
            "user_namespace_checks_passed": False,
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "code": exc.code,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    elif result.user_namespace_checks_passed:
        print("OK user namespace mapping evidence matches reviewed descriptor")
    else:
        for finding in result.findings:
            print(f"FAIL {finding}", file=sys.stderr)
    return 0 if result.user_namespace_checks_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
