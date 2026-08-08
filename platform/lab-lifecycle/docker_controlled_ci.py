from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

CONTROL_LABEL = "hex0r.controlled-ci"
LAB_LABEL = "hex0r.lab_id"
CAMPAIGN_LABEL = "hex0r.campaign_id"
MAX_SCAN_CYCLES = 10


class ControlledDockerError(RuntimeError):
    """Fail-closed controlled Docker lifecycle error."""


def _docker() -> str:
    binary = shutil.which("docker")
    if not binary:
        raise ControlledDockerError("docker CLI unavailable")
    return binary


def _run(args: list[str], *, timeout: int = 10) -> str:
    result = subprocess.run(
        [_docker(), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise ControlledDockerError("controlled Docker command failed")
    return result.stdout.strip()


def _parse_labels(value: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in filter(None, (part.strip() for part in value.split(","))):
        key, sep, val = item.partition("=")
        if sep:
            labels[key] = val
    return labels


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ControlledResources:
    lab_id: str
    campaign_id: str
    network_name: str
    volume_name: str


class ControlledDockerLab:
    """CI-only Docker network/volume lifecycle with explicit ownership labels.

    It never creates or runs containers and will only inspect/remove resources carrying
    the controlled-CI label plus the exact lab/campaign ownership labels.
    """

    def __init__(self, *, lab_id: str, campaign_id: str) -> None:
        for value in (lab_id, campaign_id):
            if not isinstance(value, str) or len(value) < 3 or len(value) > 64:
                raise ControlledDockerError("bounded lab and campaign ids are required")
            if not all(ch.isalnum() or ch in "._-" for ch in value):
                raise ControlledDockerError("lab and campaign ids contain unsupported characters")
        self.lab_id = lab_id
        self.campaign_id = campaign_id
        suffix = hashlib.sha256(f"{lab_id}:{campaign_id}".encode()).hexdigest()[:12]
        self.network_name = f"hex0r-ci-net-{suffix}"
        self.volume_name = f"hex0r-ci-vol-{suffix}"

    def provision(self) -> ControlledResources:
        labels = [
            "--label", f"{CONTROL_LABEL}=true",
            "--label", f"{LAB_LABEL}={self.lab_id}",
            "--label", f"{CAMPAIGN_LABEL}={self.campaign_id}",
        ]
        network_created = False
        try:
            _run(["network", "create", "--internal", *labels, self.network_name])
            network_created = True
            _run(["volume", "create", *labels, self.volume_name])
        except Exception:
            if network_created:
                try:
                    _run(["network", "rm", self.network_name])
                except Exception:
                    pass
            raise
        if not self.network_is_internal():
            self.cleanup_with_state(cleanup_attempt_id="provision-failure")
            raise ControlledDockerError("controlled network is not internal")
        return ControlledResources(self.lab_id, self.campaign_id, self.network_name, self.volume_name)

    def network_is_internal(self) -> bool:
        return _run(["network", "inspect", self.network_name, "--format", "{{.Internal}}"] ).lower() == "true"

    def cleanup(self, *, cleanup_attempt_id: str, observed_at: str | None = None) -> dict[str, Any]:
        self._assert_owned("network", self.network_name)
        self._assert_owned("volume", self.volume_name)
        _run(["volume", "rm", self.volume_name])
        _run(["network", "rm", self.network_name])
        remaining = [
            item for item in scan_controlled_resources(lifecycle_records=[], observed_at=observed_at or _now())["resources"]
            if item["lab_id"] == self.lab_id and item["campaign_id"] == self.campaign_id
        ]
        if remaining:
            raise ControlledDockerError("zero-residue verification failed")
        proof = {
            "schema_version": "1.0.0",
            "proof_id": f"proof-{hashlib.sha256((self.lab_id + cleanup_attempt_id).encode()).hexdigest()[:20]}",
            "lab_id": self.lab_id,
            "campaign_id": self.campaign_id,
            "cleanup_attempt_id": cleanup_attempt_id,
            "observed_at": observed_at or _now(),
            "scanner_state": "COMPLETE",
            "resources": {"containers": [], "networks": [], "volumes": [], "processes": [], "mounts": []},
            "temporary_paths": [],
            "network_absent": True,
        }
        proof["verification_sha256"] = _digest(proof)
        return proof

    def cleanup_with_state(self, *, cleanup_attempt_id: str, observed_at: str | None = None) -> dict[str, Any]:
        try:
            proof = self.cleanup(cleanup_attempt_id=cleanup_attempt_id, observed_at=observed_at)
            return {"state": "VERIFIED", "reusable": True, "proof": proof, "cleanup_error": None}
        except Exception:
            return {"state": "QUARANTINED", "reusable": False, "proof": None, "cleanup_error": "CLEANUP_UNVERIFIED"}

    def _assert_owned(self, kind: str, name: str) -> None:
        raw = _run([kind, "inspect", name, "--format", "{{json .Labels}}"])
        try:
            labels = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ControlledDockerError("resource labels unavailable") from exc
        expected = {
            CONTROL_LABEL: "true",
            LAB_LABEL: self.lab_id,
            CAMPAIGN_LABEL: self.campaign_id,
        }
        if not isinstance(labels, dict) or any(labels.get(key) != value for key, value in expected.items()):
            raise ControlledDockerError("resource ownership labels do not match")


def scan_controlled_resources(
    *, lifecycle_records: Iterable[Mapping[str, Any]], observed_at: str
) -> dict[str, Any]:
    resources: list[dict[str, str]] = []
    commands = (("network", "network"), ("volume", "volume"))
    for command, kind in commands:
        output = _run([command, "ls", "--filter", f"label={CONTROL_LABEL}=true", "--format", "{{json .}}"])
        for line in filter(None, output.splitlines()):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ControlledDockerError("Docker scanner returned invalid JSON") from exc
            labels = _parse_labels(str(row.get("Labels", "")))
            lab_id = labels.get(LAB_LABEL)
            campaign_id = labels.get(CAMPAIGN_LABEL)
            resource_id = str(row.get("ID") or row.get("Name") or "")
            if not lab_id or not campaign_id or not resource_id:
                raise ControlledDockerError("controlled resource lacks ownership metadata")
            resources.append(
                {
                    "resource_ref": f"docker-{kind}:{resource_id[:24]}",
                    "kind": kind,
                    "lab_id": lab_id,
                    "campaign_id": campaign_id,
                }
            )
    resources.sort(key=lambda item: item["resource_ref"])
    seed = {"observed_at": observed_at, "resources": resources}
    return {
        "schema_version": "1.0.0",
        "observation_id": f"obs-{_digest(seed)[:24]}",
        "observed_at": observed_at,
        "scanner_state": "COMPLETE",
        "lifecycle_records": [dict(item) for item in lifecycle_records],
        "resources": resources,
    }


def periodic_scan(
    *, lifecycle_records: Iterable[Mapping[str, Any]], observed_at: str, cycles: int = 2, interval_seconds: float = 0.0
) -> list[dict[str, Any]]:
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= MAX_SCAN_CYCLES:
        raise ControlledDockerError("cycles must be between 1 and 10")
    if not isinstance(interval_seconds, (int, float)) or not 0.0 <= float(interval_seconds) <= 60.0:
        raise ControlledDockerError("scan interval is out of bounds")
    results = []
    records = [dict(item) for item in lifecycle_records]
    for index in range(cycles):
        results.append(scan_controlled_resources(lifecycle_records=records, observed_at=observed_at))
        if index + 1 < cycles and interval_seconds:
            time.sleep(float(interval_seconds))
    return results
