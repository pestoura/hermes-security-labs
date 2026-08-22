from __future__ import annotations

import importlib.util
import ipaddress
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = ROOT / "deployment" / "shared-vault-hsl" / "probe"
PROBE = PROBE_DIR / "probe.py"
DOCKERFILE = PROBE_DIR / "Dockerfile"
COMPOSE = PROBE_DIR / "compose.yaml"
README = PROBE_DIR / "README.md"
CONTRACT = ROOT / "deployment" / "shared-vault-hsl" / "consumer-contract.yaml"

EXPECTED_ADDR = "https://hermes-vault:8200"
EXPECTED_NETWORK = "hermes-security-plane"
EXPECTED_BASE = (
    "docker.io/library/python:3.12-alpine3.22@"
    "sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322"
)


def _load() -> Any:
    assert PROBE.exists(), "pre-secret-zero probe implementation is missing"
    spec = importlib.util.spec_from_file_location("chg_hsl_086_shared_vault_probe", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_artifacts_exist() -> None:
    for path in (PROBE, DOCKERFILE, COMPOSE, README):
        assert path.exists(), f"missing CHG-HSL-086 artifact: {path.relative_to(ROOT)}"


def test_probe_endpoint_matches_accepted_consumer_contract() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["shared-vault-probe"]
    assert contract["vault_addr"] == EXPECTED_ADDR
    assert service["environment"]["HSL_VAULT_ADDR"] == EXPECTED_ADDR
    assert compose["networks"]["hermes-security-plane"]["name"] == EXPECTED_NETWORK
    assert compose["networks"]["hermes-security-plane"]["external"] is True
    assert list(service["networks"]) == ["hermes-security-plane"]


def test_probe_compose_is_disposable_and_hardened() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["shared-vault-probe"]
    assert service["restart"] == "no"
    assert service["read_only"] is True
    assert service["user"] == "10001:10001"
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service.get("ports") in (None, [])
    serialized = json.dumps(service, sort_keys=True)
    assert "docker.sock" not in serialized
    assert "privileged" not in serialized
    assert "network_mode" not in serialized
    assert "hsl-shared-vault-ca:/run/hsl-vault-ca:ro" in serialized
    assert compose["volumes"]["hsl-shared-vault-ca"]["external"] is True
    assert compose["volumes"]["hsl-shared-vault-ca"]["name"] == "hsl-shared-vault-ca"
    assert service["deploy"]["resources"]["limits"] == {"cpus": "0.25", "memory": "64M", "pids": 32}


def test_probe_image_is_pinned_and_non_root() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert f"FROM {EXPECTED_BASE}" in text
    assert "USER 10001:10001" in text
    assert "ENTRYPOINT" in text and "probe.py" in text
    assert " apk add " not in f" {text.lower()} "
    assert "pip install" not in text.lower()


def test_probe_code_has_no_credential_handling_surface() -> None:
    text = PROBE.read_text(encoding="utf-8").lower()
    for forbidden in (
        "role_id",
        "secret_id",
        "wrapping_token",
        "vault_token",
        "x-vault-token",
        "/auth/approle/",
        "/sys/wrapping/",
    ):
        assert forbidden not in text


def test_endpoint_parser_is_exact_and_fail_closed() -> None:
    probe = _load()
    endpoint = probe.parse_vault_endpoint(EXPECTED_ADDR)
    assert endpoint.host == "hermes-vault"
    assert endpoint.port == 8200
    assert endpoint.url == EXPECTED_ADDR
    for bad in (
        "http://hermes-vault:8200",
        "https://127.0.0.1:8200",
        "https://hermes-vault:8201",
        "https://hermes-vault:8200/v1/sys/health",
        "https://user@hermes-vault:8200",
        "https://hermes-vault:8200?x=1",
    ):
        with pytest.raises(probe.ProbeError) as excinfo:
            probe.parse_vault_endpoint(bad)
        assert excinfo.value.code == "VAULT_ENDPOINT_INVALID"


def test_readiness_record_is_closed_sanitized_and_no_authority() -> None:
    probe = _load()
    record = probe.build_readiness_record(
        vault_addr=EXPECTED_ADDR,
        peer_ip="172.25.0.2",
        consumer_ip="172.25.0.9",
        tls_version="TLSv1.3",
    )
    assert set(record) == {
        "schema_version",
        "provider",
        "vault_addr",
        "peer_ip",
        "consumer_cidr",
        "dns_resolved",
        "tls_verified",
        "tls_version",
        "credential_stage",
        "runtime_status",
        "promotion_allowed",
        "execution_authority",
    }
    assert record["consumer_cidr"] == "172.25.0.9/32"
    assert ipaddress.ip_network(record["consumer_cidr"]).prefixlen == 32
    assert record["credential_stage"] == "NOT_RUN"
    assert record["runtime_status"] == "OBSERVED_PRE_SECRET_ZERO"
    assert record["promotion_allowed"] is False
    assert record["execution_authority"] == "NONE"
    serialized = json.dumps(record).lower()
    for forbidden in ("vault_token", "secret_id", "role_id", "wrapping_token", "passphrase", "private_key"):
        assert forbidden not in serialized


def test_invalid_or_non_ipv4_readiness_fails_closed() -> None:
    probe = _load()
    for consumer_ip in ("not-an-ip", "2001:db8::1"):
        with pytest.raises(probe.ProbeError) as excinfo:
            probe.build_readiness_record(
                vault_addr=EXPECTED_ADDR,
                peer_ip="172.25.0.2",
                consumer_ip=consumer_ip,
                tls_version="TLSv1.3",
            )
        assert excinfo.value.code == "PROBE_NETWORK_IDENTITY_INVALID"


def test_readme_preserves_pre_secret_zero_boundary() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "PRE_SECRET_ZERO_NETWORK_READY",
        "SECRETID_ISSUANCE=NOT_RUN",
        "NO_AUTOMATIC_FALLBACK",
        "promotion_allowed=false",
        "execution_authority=NONE",
    ):
        assert marker in text


class _FakeRawSocket:
    def getpeername(self):
        return ("172.25.0.2", 8200)

    def getsockname(self):
        return ("172.25.0.9", 41000)


class _FakeTLSSocket:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getpeercert(self):
        return {"subject": (("commonName", "hermes-vault"),)}

    def version(self):
        return "TLSv1.3"


class _FakeTLSContext:
    def __init__(self) -> None:
        self.check_hostname = False
        self.verify_mode = 0
        self.server_hostname = None

    def wrap_socket(self, raw, *, server_hostname):
        assert isinstance(raw, _FakeRawSocket)
        self.server_hostname = server_hostname
        return _FakeTLSSocket()


def test_probe_once_enforces_ca_hostname_and_source_identity(tmp_path: Path) -> None:
    probe = _load()
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-public-ca", encoding="utf-8")
    context = _FakeTLSContext()
    captured = {}

    def context_factory(*, cafile):
        captured["cafile"] = cafile
        return context

    def connector(address, *, timeout):
        captured["address"] = address
        captured["timeout"] = timeout
        return _FakeRawSocket()
    record = probe.probe_once(
        EXPECTED_ADDR,
        str(ca),
        connector=connector,
        context_factory=context_factory,
    )
    assert captured["cafile"] == str(ca)
    assert captured["address"] == ("hermes-vault", 8200)
    assert captured["timeout"] == 3.0
    assert context.check_hostname is True
    assert context.verify_mode != 0
    assert context.server_hostname == "hermes-vault"
    assert record["peer_ip"] == "172.25.0.2"
    assert record["consumer_cidr"] == "172.25.0.9/32"
    assert record["tls_verified"] is True


def test_probe_once_fails_closed_on_connect_error(tmp_path: Path) -> None:
    probe = _load()
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-public-ca", encoding="utf-8")

    def connector(*_args, **_kwargs):
        raise OSError("synthetic unreachable")

    with pytest.raises(probe.ProbeError) as excinfo:
        probe.probe_once(EXPECTED_ADDR, str(ca), connector=connector)
    assert excinfo.value.code == "VAULT_TLS_PROBE_FAILED"
