#!/usr/bin/env python3
"""Read-only host evidence collector for Runner live-promotion prerequisites.

The collector observes declared service accounts, dispatch group membership,
AF_UNIX socket/directory ownership and the installed public TB1 trust store. It
never provisions users, changes permissions, creates sockets, reads a private
key, contacts a signer or promotes a policy.

A host-evidence PASS is intentionally partial: user-namespace mapping, external
signer attestation, unauthorized-peer negative tests and live audit/effect
observations remain separate required evidence.
"""

from __future__ import annotations

import argparse
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
SCHEMA_PATH = HERE / "runtime-host-evidence-descriptor.schema.json"
DEFAULT_DESCRIPTOR = HERE / "templates" / "runtime-host-evidence-descriptor.example.yaml"
IDENTITY_PREFLIGHT_PATH = HERE / "runner_identity_preflight.py"
TB1_PREFLIGHT_PATH = HERE / "tb1_authorization_preflight.py"

REMAINING_EVIDENCE = (
    "USER_NAMESPACE_MAPPING_NOT_OBSERVED",
    "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED",
    "UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN",
    "LIVE_AUDIT_SINK_NOT_OBSERVED",
    "LIVE_RUNNER_EFFECT_NOT_RUN",
)


class HostEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PathObservation:
    exists: bool
    kind: str | None = None
    uid: int | None = None
    gid: int | None = None
    mode: str | None = None
    symlink: bool = False


class HostObserver(Protocol):
    def user(self, name: str) -> Mapping[str, Any] | None:
        ...

    def group(self, name: str) -> Mapping[str, Any] | None:
        ...

    def path(self, path: str) -> PathObservation:
        ...

    def json_document(self, path: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class HostEvidenceResult:
    host_checks_passed: bool
    promotion_allowed: bool
    runtime_status: str
    findings: tuple[str, ...]
    remaining_evidence: tuple[str, ...]
    observations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "host_checks_passed": self.host_checks_passed,
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
        raise RuntimeError(f"cannot load canonical preflight {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identity_preflight = _load_module(
    "runtime_host_evidence_identity_preflight", IDENTITY_PREFLIGHT_PATH
)
tb1_preflight = _load_module("runtime_host_evidence_tb1_preflight", TB1_PREFLIGHT_PATH)


def _safe_repo_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise HostEvidenceError("DESCRIPTOR_PATH_INVALID", "descriptor references must be relative")
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise HostEvidenceError(
            "DESCRIPTOR_PATH_INVALID", "descriptor reference escapes repository root"
        ) from exc
    return path


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise HostEvidenceError(code, f"cannot load {path.name}") from exc
    if not isinstance(document, dict):
        raise HostEvidenceError(code, f"{path.name} must contain an object")
    return document


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise HostEvidenceError(code, f"cannot load {path.name}") from exc
    if not isinstance(document, dict):
        raise HostEvidenceError(code, f"{path.name} must contain an object")
    return document


def _validate_descriptor(document: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH, "DESCRIPTOR_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise HostEvidenceError("DESCRIPTOR_INVALID", f"{location}: {first.message}")
    _safe_repo_path(document["identity_descriptor"])
    _safe_repo_path(document["tb1_descriptor"])


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    document = _load_yaml(path, "DESCRIPTOR_UNREADABLE")
    _validate_descriptor(document)
    return document


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _kind(mode: int) -> str:
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


class RealHostObserver:
    """Standard-library, non-privileged host observer."""

    def user(self, name: str) -> Mapping[str, Any] | None:
        try:
            entry = pwd.getpwnam(name)
        except KeyError:
            return None
        return {
            "user": entry.pw_name,
            "uid": entry.pw_uid,
            "gid": entry.pw_gid,
            "shell": entry.pw_shell,
        }

    def group(self, name: str) -> Mapping[str, Any] | None:
        try:
            entry = grp.getgrnam(name)
        except KeyError:
            return None
        members = set(entry.gr_mem)
        for account in pwd.getpwall():
            if account.pw_gid == entry.gr_gid:
                members.add(account.pw_name)
        return {"group": entry.gr_name, "gid": entry.gr_gid, "members": sorted(members)}

    def path(self, path: str) -> PathObservation:
        try:
            result = os.lstat(path)
        except FileNotFoundError:
            return PathObservation(exists=False)
        return PathObservation(
            exists=True,
            kind=_kind(result.st_mode),
            uid=result.st_uid,
            gid=result.st_gid,
            mode=f"0{stat.S_IMODE(result.st_mode):03o}",
            symlink=stat.S_ISLNK(result.st_mode),
        )

    def json_document(self, path: str) -> Mapping[str, Any]:
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise HostEvidenceError(
                "TRUST_STORE_UNREADABLE", "installed trust store cannot be read as JSON"
            ) from exc
        if not isinstance(document, Mapping):
            raise HostEvidenceError("TRUST_STORE_INVALID", "installed trust store must be an object")
        return dict(document)


def _observe_identity(
    role: str,
    expected: Mapping[str, Any],
    observer: HostObserver,
    findings: list[str],
) -> dict[str, Any]:
    actual = observer.user(str(expected["user"]))
    if actual is None:
        findings.append(f"{role} account {expected['user']} is absent")
        return {"present": False}
    for field in ("uid", "gid", "shell"):
        if actual.get(field) != expected.get(field):
            findings.append(
                f"{role} account {field} mismatch: expected {expected.get(field)!r}, observed {actual.get(field)!r}"
            )
    return {
        "present": True,
        "user": actual.get("user"),
        "uid": actual.get("uid"),
        "gid": actual.get("gid"),
        "shell": actual.get("shell"),
    }


def _observe_path(
    label: str,
    path: str,
    expected_kind: str,
    expected_uid: int,
    expected_gid: int,
    expected_mode: str,
    observer: HostObserver,
    findings: list[str],
) -> dict[str, Any]:
    actual = observer.path(path)
    if not actual.exists:
        findings.append(f"{label} is absent: {path}")
        return {"path": path, "present": False}
    if actual.symlink:
        findings.append(f"{label} must not be a symlink: {path}")
    for field, expected, observed in (
        ("kind", expected_kind, actual.kind),
        ("uid", expected_uid, actual.uid),
        ("gid", expected_gid, actual.gid),
        ("mode", expected_mode, actual.mode),
    ):
        if observed != expected:
            findings.append(
                f"{label} {field} mismatch: expected {expected!r}, observed {observed!r}"
            )
    return {
        "path": path,
        "present": True,
        "kind": actual.kind,
        "uid": actual.uid,
        "gid": actual.gid,
        "mode": actual.mode,
        "symlink": actual.symlink,
    }


def collect_host_evidence(
    descriptor: Mapping[str, Any],
    *,
    observer: HostObserver | None = None,
) -> HostEvidenceResult:
    _validate_descriptor(descriptor)
    host = observer or RealHostObserver()

    identity_path = _safe_repo_path(descriptor["identity_descriptor"])
    identity_document = identity_preflight.load_descriptor(identity_path)
    identity_result = identity_preflight.run_preflight(identity_document)
    if not identity_result.ok:
        raise HostEvidenceError(
            "IDENTITY_DESCRIPTOR_INVALID", "; ".join(identity_result.findings)
        )

    tb1_path = _safe_repo_path(descriptor["tb1_descriptor"])
    tb1_document = tb1_preflight.load_descriptor(tb1_path)
    tb1_result = tb1_preflight.run_preflight(tb1_document)
    if not tb1_result.ok:
        raise HostEvidenceError("TB1_DESCRIPTOR_INVALID", "; ".join(tb1_result.findings))

    findings: list[str] = []
    identities = identity_document["identities"]
    observations: dict[str, Any] = {
        "gateway": _observe_identity(
            "gateway", identities["gateway"], host, findings
        ),
        "runner": _observe_identity("runner", identities["runner"], host, findings),
    }

    group_expected = identities["dispatch_group"]
    group_actual = host.group(str(group_expected["group"]))
    if group_actual is None:
        findings.append(f"dispatch group {group_expected['group']} is absent")
        observations["dispatch_group"] = {"present": False}
    else:
        if group_actual.get("gid") != group_expected.get("gid"):
            findings.append(
                f"dispatch group gid mismatch: expected {group_expected.get('gid')}, observed {group_actual.get('gid')}"
            )
        observed_members = set(group_actual.get("members", []))
        expected_members = set(group_expected.get("members", []))
        missing = sorted(expected_members - observed_members)
        if missing:
            findings.append(f"dispatch group missing expected members: {missing}")
        observations["dispatch_group"] = {
            "present": True,
            "group": group_actual.get("group"),
            "gid": group_actual.get("gid"),
            "expected_members_present": not missing,
        }

    socket_expected = identity_document["socket"]
    directory_expected = socket_expected["directory"]
    observations["socket_directory"] = _observe_path(
        "socket directory",
        str(directory_expected["path"]),
        "directory",
        int(directory_expected["owner_uid"]),
        int(directory_expected["group_gid"]),
        str(directory_expected["mode"]),
        host,
        findings,
    )
    observations["socket"] = _observe_path(
        "Runner dispatch socket",
        str(socket_expected["path"]),
        "socket",
        int(socket_expected["owner_uid"]),
        int(socket_expected["group_gid"]),
        str(socket_expected["mode"]),
        host,
        findings,
    )

    trust_path = str(tb1_document["trust_store"]["install_path"])
    trust_expectation = descriptor["trust_store_expectation"]
    observations["trust_store"] = _observe_path(
        "Runner authorization trust store",
        trust_path,
        "file",
        int(trust_expectation["owner_uid"]),
        int(trust_expectation["group_gid"]),
        str(trust_expectation["mode"]),
        host,
        findings,
    )
    gateway_uid = int(identities["gateway"]["uid"])
    runner_uid = int(identities["runner"]["uid"])
    if trust_expectation["owner_uid"] in {gateway_uid, runner_uid}:
        findings.append("trust-store owner must be independent of gateway and Runner identities")

    trust_observation = observations["trust_store"]
    if trust_observation.get("present") and not trust_observation.get("symlink"):
        try:
            installed = host.json_document(trust_path)
        except HostEvidenceError as exc:
            findings.append(str(exc))
        else:
            declared = tb1_document["trust_store"]["document"]
            installed_sha = _canonical_sha256(installed)
            declared_sha = _canonical_sha256(declared)
            trust_observation["document_sha256"] = installed_sha
            trust_observation["declared_sha256"] = declared_sha
            trust_observation["document_matches_declaration"] = installed_sha == declared_sha
            if installed_sha != declared_sha:
                findings.append("installed trust-store document does not match approved declaration")

    return HostEvidenceResult(
        host_checks_passed=not findings,
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
        result = collect_host_evidence(descriptor)
    except HostEvidenceError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "host_checks_passed": False,
                        "promotion_allowed": False,
                        "runtime_status": "NOT_RUN",
                        "code": exc.code,
                        "error": str(exc),
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"FAIL-CLOSED [{exc.code}] {exc}")
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        state = "PASS" if result.host_checks_passed else "FAIL-CLOSED"
        print(
            f"{state} runtime_status=NOT_RUN promotion_allowed=false "
            f"remaining_evidence={len(result.remaining_evidence)}"
        )
        for finding in result.findings:
            print(f"- {finding}")
    return 0 if result.host_checks_passed else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
