from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_DIR = ROOT / "platform" / "lab-lifecycle"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, LIFECYCLE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


docker_ci = _load("b03_docker_controlled_test", "docker_controlled_ci.py")
orphan = _load("b03_orphan_assessor_test", "orphan_detector.py")


def _require_docker() -> str:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI unavailable")
    result = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        pytest.skip("Docker daemon unavailable")
    return docker


def _ids() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:12]
    return f"lab-{suffix}", f"campaign-{suffix}"


def _record(lab_id: str, campaign_id: str, state: str = "RUNNING") -> dict:
    return {
        "lab_id": lab_id,
        "campaign_id": campaign_id,
        "state": state,
        "contract_expires_at": "2026-08-09T22:00:00Z",
        "quarantine_retention_until": None,
    }


def test_real_docker_network_is_internal_and_scanner_observes_only_owned_resources() -> None:
    _require_docker()
    lab_id, campaign_id = _ids()
    lab = docker_ci.ControlledDockerLab(lab_id=lab_id, campaign_id=campaign_id)
    lab.provision()
    try:
        assert lab.network_is_internal() is True
        observation = docker_ci.scan_controlled_resources(
            lifecycle_records=[_record(lab_id, campaign_id)], observed_at="2026-08-08T22:00:00Z"
        )
        owned = [r for r in observation["resources"] if r["lab_id"] == lab_id]
        assert {r["kind"] for r in owned} == {"network", "volume"}
        result = orphan.assess_orphans(observation)
        assert result.result == "CLEAR"
        assert result.orphan_count == 0
    finally:
        state = lab.cleanup_with_state(cleanup_attempt_id="cleanup-finally", observed_at="2026-08-08T22:01:00Z")
        assert state["state"] == "VERIFIED"


def test_periodic_real_scans_detect_untracked_controlled_resources_then_cleanup_proves_zero_residue() -> None:
    _require_docker()
    lab_id, campaign_id = _ids()
    lab = docker_ci.ControlledDockerLab(lab_id=lab_id, campaign_id=campaign_id)
    lab.provision()
    cleaned = False
    try:
        observations = docker_ci.periodic_scan(
            lifecycle_records=[], observed_at="2026-08-08T22:02:00Z", cycles=2, interval_seconds=0
        )
        assert len(observations) == 2
        for observation in observations:
            assessment = orphan.assess_orphans(observation)
            assert assessment.result == "ORPHANS_DETECTED"
            assert assessment.orphan_count >= 2

        proof = lab.cleanup(cleanup_attempt_id="cleanup-1", observed_at="2026-08-08T22:03:00Z")
        cleaned = True
        schema = json.loads((LIFECYCLE_DIR / "zero-residue-proof.schema.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(proof)
        assert proof["network_absent"] is True
        assert all(not values for values in proof["resources"].values())
        after = docker_ci.scan_controlled_resources(lifecycle_records=[], observed_at="2026-08-08T22:04:00Z")
        assert all(r["lab_id"] != lab_id for r in after["resources"])
    finally:
        if not cleaned:
            lab.cleanup_with_state(cleanup_attempt_id="cleanup-finally", observed_at="2026-08-08T22:05:00Z")


def test_cleanup_failure_is_fail_closed_to_quarantine(monkeypatch: pytest.MonkeyPatch) -> None:
    lab = docker_ci.ControlledDockerLab(lab_id="lab-synthetic", campaign_id="campaign-synthetic")
    monkeypatch.setattr(lab, "_assert_owned", lambda *args, **kwargs: None)

    def fail(*args, **kwargs):
        raise docker_ci.ControlledDockerError("synthetic cleanup failure")

    monkeypatch.setattr(docker_ci, "_run", fail)
    result = lab.cleanup_with_state(cleanup_attempt_id="cleanup-failure", observed_at="2026-08-08T22:06:00Z")
    assert result == {
        "state": "QUARANTINED",
        "reusable": False,
        "proof": None,
        "cleanup_error": "CLEANUP_UNVERIFIED",
    }


def test_periodic_scan_is_bounded() -> None:
    with pytest.raises(docker_ci.ControlledDockerError):
        docker_ci.periodic_scan(lifecycle_records=[], observed_at="2026-08-08T22:07:00Z", cycles=11)
