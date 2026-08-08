from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs/architecture/phase4-vm-infrastructure-ad.md"
VM = ROOT / "platform/environments/infrastructure/metasploitable-vm-pilot.yaml"
GOAD = ROOT / "platform/environments/active-directory/goad-mini-future.yaml"
NETWORK = ROOT / "platform/environments/infrastructure/network-emulation-future-hardware.yaml"
RUNTIME = ROOT / "platform/runtimes/virtual-machine.yaml"


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_phase4_architecture_records_required_drivers_budgets_and_migration() -> None:
    text = ARCH.read_text(encoding="utf-8")
    for driver in ("libvirt", "proxmox", "external-hypervisor"):
        assert f"`{driver}`" in text
    assert "GOAD Mini" in text
    assert "Metasploitable Linux pilot" in text
    assert "EVE-NG/GNS3" in text
    assert "Proxmox bare metal or a second dedicated host" in text
    assert "read-only KVM/libvirt capability discovery" in text
    assert "does not claim a deployed VM runtime" in text


def test_vm_pilot_and_goad_remain_future_vm_with_bounded_resources() -> None:
    for manifest in (_load(VM), _load(GOAD)):
        assert manifest["runtime"] == "virtual-machine"
        assert manifest["status"] == "FUTURE-VM"
        assert manifest["egress"] is False
        assert manifest["resources"]["max_concurrent"] == 1
        assert manifest["targets"] == []
        assert manifest["reset"]
        assert manifest["cleanup"] == "zero-residue-proof-required"
        assert {"create", "start", "status", "stop", "reset", "destroy"}.issubset(manifest["lifecycle"])


def test_heavy_network_emulation_is_future_hardware_and_not_startable() -> None:
    manifest = _load(NETWORK)
    assert manifest["status"] == "FUTURE-HARDWARE"
    assert manifest["resources"]["max_concurrent"] == 0
    assert manifest["lifecycle"] == ["status"]
    assert manifest["egress"] is False


def test_current_vm_runtime_preserves_read_only_design_boundary() -> None:
    runtime = _load(RUNTIME)
    assert runtime["status"] == "CURRENT-LIMITED"
    assert runtime["drivers"] == ["libvirt", "proxmox", "external-hypervisor"]
    assert runtime["lifecycle"] == ["status"]
    limitations = " ".join(runtime["limitations"])
    assert "No Proxmox or libvirt installation" in limitations
    assert "read-only KVM audit" in limitations
