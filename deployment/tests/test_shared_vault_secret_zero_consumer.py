from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "deployment" / "shared-vault-hsl" / "consumer"
DOCKERFILE = CONSUMER / "Dockerfile"
COMPOSE = CONSUMER / "compose.yaml"

VAULT_IMAGE = (
    "hashicorp/vault:1.21.4@sha256:"
    "4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569"
)
RUNTIME_IMAGE = (
    "docker.io/library/python:3.12-alpine3.22@sha256:"
    "a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322"
)


def _compose_service() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return document["services"]["secret-zero-consumer"]


def test_consumer_image_is_dedicated_pinned_and_non_volume_inheriting() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")
    assert f"FROM {VAULT_IMAGE} AS vaultcli" in source
    assert f"FROM {RUNTIME_IMAGE}" in source
    assert "COPY --from=vaultcli /bin/vault /usr/local/bin/vault" in source
    assert "USER 10001:10001" in source
    assert "VOLUME" not in source
    assert "VAULT_TOKEN" not in source
    assert "SECRET_ID" not in source
    assert "WRAP_TOKEN" not in source
    assert "ROLE_ID" not in source


def test_consumer_compose_is_fail_closed_and_uses_isolated_external_network() -> None:
    service = _compose_service()
    assert service["container_name"] == "hsl-secret-zero-consumer"
    assert "network_mode" not in service
    assert service["networks"] == ["hermes-security-plane"]
    assert service["user"] == "10001:10001"
    assert service["read_only"] is True
    assert service["restart"] == "no"
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["privileged"] is False
    assert service["stdin_open"] is True
    assert service["tty"] is True


def test_consumer_mounts_only_public_ca_read_only_and_ephemeral_tmp() -> None:
    service = _compose_service()
    volumes = service.get("volumes", [])
    assert volumes == ["hsl-shared-vault-ca:/run/hsl-vault-ca:ro"]
    assert all("/vault/file" not in item for item in volumes)
    assert all("/vault/logs" not in item for item in volumes)
    assert service["tmpfs"] == ["/tmp:rw,noexec,nosuid,nodev,size=16m"]
    environment = service["environment"]
    assert environment == {
        "VAULT_ADDR": "https://hermes-vault:8200",
        "VAULT_CACERT": "/run/hsl-vault-ca/ca.pem",
    }


def test_consumer_has_bounded_resources_and_external_ca_volume() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = document["services"]["secret-zero-consumer"]
    limits = service["deploy"]["resources"]["limits"]
    assert limits == {"cpus": "0.25", "memory": "96M", "pids": 32}
    assert document["networks"]["hermes-security-plane"] == {
        "external": True,
        "name": "hermes-security-plane",
    }
    assert document["volumes"]["hsl-shared-vault-ca"] == {
        "external": True,
        "name": "hsl-shared-vault-ca",
    }
