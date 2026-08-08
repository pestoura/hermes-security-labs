from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "platform/domain-preparation/phase5-policy.yaml"
DOC = ROOT / "docs/architecture/phase5-cloud-mobile-iot-ot.md"
CLOUD_RUNTIME = ROOT / "platform/runtimes/cloud.yaml"
EMULATOR_RUNTIME = ROOT / "platform/runtimes/emulator.yaml"


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_phase5_policy_has_no_execution_or_activation_authority() -> None:
    policy = _load(POLICY)
    assert policy["execution_authority"] == "NONE"
    assert policy["real_cloud_resources_created"] is False
    assert policy["host_emulator_installation"] is False
    assert policy["external_hardware_activation"] is False
    assert policy["firmware_payloads_in_git"] is False
    assert policy["credentials_in_git"] is False
    assert all(domain["activation"] is False for domain in policy["domains"].values())


def test_required_phase5_classifications_are_explicit() -> None:
    domains = _load(POLICY)["domains"]
    assert domains["local-cloud-emulation"]["classification"] == "CURRENT-LIMITED"
    assert domains["cloud-sandbox"]["classification"] == "CLOUD-SANDBOX"
    assert domains["mobile-emulation"]["classification"] == "FUTURE-HARDWARE"
    assert domains["firmware-analysis"]["classification"] == "FUTURE-HARDWARE"
    assert domains["iot-ot-simulation"]["classification"] == "FUTURE-HARDWARE"
    assert domains["external-rf-ot-hardware"]["classification"] == "EXTERNAL-HARDWARE"


def test_cloud_and_external_hardware_admission_is_fail_closed() -> None:
    admission = _load(POLICY)["admission"]
    assert admission == {
        "default": "deny",
        "requires_cleanup_evidence": True,
        "cloud_requires_ephemeral_credentials": True,
        "cloud_requires_budget": True,
        "cloud_requires_ttl": True,
        "external_hardware_requires_human_approval": True,
    }


def test_runtime_profiles_remain_non_activating() -> None:
    cloud = _load(CLOUD_RUNTIME)
    emulator = _load(EMULATOR_RUNTIME)
    assert cloud["status"] == "CLOUD-SANDBOX"
    assert cloud["lifecycle"] == ["status"]
    assert cloud["isolation"]["default_egress"] is False
    assert emulator["status"] == "EXTERNAL-HARDWARE"
    assert emulator["lifecycle"] == ["status"]
    assert emulator["isolation"]["default_egress"] is False


def test_architecture_explicitly_preserves_non_execution_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "creates no AWS, Azure or GCP resource" in text
    assert "installs no emulator on the Hermes host" in text
    assert "activates no external hardware" in text
    assert "Human-in-the-Loop approval" in text
    assert "remain future separately authorized work" in text
