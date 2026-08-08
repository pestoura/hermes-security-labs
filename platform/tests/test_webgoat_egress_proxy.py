from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "platform/environments/web-api/webgoat/compose.yaml"
MANIFEST = ROOT / "platform/environments/web-api/webgoat/manifest.yaml"


def _compose() -> dict:
    value = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_webgoat_has_no_host_ports_and_only_internal_network() -> None:
    data = _compose()
    webgoat = data["services"]["webgoat"]
    assert "ports" not in webgoat
    assert webgoat["networks"] == ["webgoat-lab"]
    assert data["networks"]["webgoat-lab"]["internal"] is True


def test_proxy_is_the_only_dual_homed_localhost_publisher() -> None:
    data = _compose()
    proxy = data["services"]["webgoat-proxy"]
    assert proxy["networks"] == ["webgoat-lab", "webgoat-publish"]
    assert data["networks"]["webgoat-publish"]["internal"] is False
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["all"]
    assert proxy["security_opt"] == ["no-new-privileges:true"]
    assert all(str(port).startswith("127.0.0.1:") for port in proxy["ports"])
    command = " ".join(proxy["command"])
    assert "TCP:webgoat:8080" in command
    assert "TCP:webgoat:9090" in command


def test_manifest_records_workload_egress_as_disabled() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["egress"] is False
    assert manifest["networks"] == ["webgoat-lab", "webgoat-publish"]
    limitations = " ".join(manifest["limitations"])
    assert "workload is attached only to the internal webgoat-lab network" in limitations
    assert "Kali attaches temporarily" in limitations
