from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "kali-mcp/compose.yaml"


def _service(name: str) -> dict:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return data["services"][name]


def test_kali_mcp_keeps_rootfs_read_only_and_drops_all_capabilities() -> None:
    service = _service("kali-mcp")
    assert service["read_only"] is True
    assert service["cap_drop"] == ["all"]
    assert service["security_opt"] == ["no-new-privileges"]
    assert "privileged" not in service
    assert "cap_add" not in service
    assert "docker.sock" not in COMPOSE.read_text(encoding="utf-8")


def test_tool_state_is_minimal_and_explicit() -> None:
    for name in ("kali-mcp", "kali-maintenance"):
        tmpfs = _service(name)["tmpfs"]
        assert any(item.startswith("/root/.wpscan:") for item in tmpfs)
        assert any(item.startswith("/root/.cache:") for item in tmpfs)
        assert any(item.startswith("/root/.john:") for item in tmpfs)
        assert any(item.startswith("/root/.msf4:") for item in tmpfs)
        assert not any(item.startswith("/root:") for item in tmpfs)


def test_normal_kali_network_remains_internal() -> None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert data["networks"]["hermes-kali-lab"]["internal"] is True
    assert _service("kali-mcp")["networks"] == ["hermes-kali-lab"]
