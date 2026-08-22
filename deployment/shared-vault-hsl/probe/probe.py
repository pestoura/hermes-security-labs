#!/usr/bin/env python3
"""Credential-free shared Vault network/TLS observation probe."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import socket
import ssl
import sys
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

EXPECTED_VAULT_ADDR = "https://hermes-vault:8200"
DEFAULT_CA_FILE = "/run/hsl-vault-ca/ca.pem"
_ALLOWED_TLS = frozenset({"TLSv1.2", "TLSv1.3"})


class ProbeError(RuntimeError):
    """Stable fail-closed probe error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

@dataclass(frozen=True)
class VaultEndpoint:
    url: str
    host: str
    port: int


def parse_vault_endpoint(value: object) -> VaultEndpoint:
    if not isinstance(value, str) or value != EXPECTED_VAULT_ADDR:
        raise ProbeError("VAULT_ENDPOINT_INVALID")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProbeError("VAULT_ENDPOINT_INVALID") from None
    if not (
        parsed.scheme == "https"
        and parsed.hostname == "hermes-vault"
        and port == 8200
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    ):
        raise ProbeError("VAULT_ENDPOINT_INVALID")
    return VaultEndpoint(url=EXPECTED_VAULT_ADDR, host="hermes-vault", port=8200)


def _ipv4(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        raise ProbeError("PROBE_NETWORK_IDENTITY_INVALID") from None
    if address.version != 4:
        raise ProbeError("PROBE_NETWORK_IDENTITY_INVALID")
    return str(address)


def build_readiness_record(
    *, vault_addr: str, peer_ip: str, consumer_ip: str, tls_version: str
) -> dict[str, Any]:
    parse_vault_endpoint(vault_addr)
    peer = _ipv4(peer_ip)
    consumer = _ipv4(consumer_ip)
    if tls_version not in _ALLOWED_TLS:
        raise ProbeError("TLS_VERSION_INVALID")
    return {
        "schema_version": "hsl.shared-vault-pre-secret-zero/v1",
        "provider": "hermes-shared-vault",
        "vault_addr": EXPECTED_VAULT_ADDR,
        "peer_ip": peer,
        "consumer_cidr": f"{consumer}/32",
        "dns_resolved": True,
        "tls_verified": True,
        "tls_version": tls_version,
        "credential_stage": "NOT_RUN",
        "runtime_status": "OBSERVED_PRE_SECRET_ZERO",
        "promotion_allowed": False,
        "execution_authority": "NONE",
    }


def probe_once(
    vault_addr: str,
    ca_file: str,
    *,
    timeout_seconds: float = 3.0,
    connector: Callable[..., Any] = socket.create_connection,
    context_factory: Callable[..., Any] = ssl.create_default_context,
) -> dict[str, Any]:
    endpoint = parse_vault_endpoint(vault_addr)
    ca_path = Path(ca_file)
    if not ca_path.is_absolute() or not ca_path.is_file():
        raise ProbeError("VAULT_CA_UNAVAILABLE")
    if not (0.25 <= float(timeout_seconds) <= 10.0):
        raise ProbeError("PROBE_TIMEOUT_INVALID")
    try:
        context = context_factory(cafile=str(ca_path))
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        raw = connector((endpoint.host, endpoint.port), timeout=float(timeout_seconds))
        consumer_ip = raw.getsockname()[0]
        peer_ip = raw.getpeername()[0]
        with context.wrap_socket(raw, server_hostname=endpoint.host) as tls_socket:
            tls_socket.getpeercert()
            tls_version = tls_socket.version()
    except ProbeError:
        raise
    except (OSError, ssl.SSLError, ValueError):
        raise ProbeError("VAULT_TLS_PROBE_FAILED") from None
    return build_readiness_record(
        vault_addr=endpoint.url,
        peer_ip=peer_ip,
        consumer_ip=consumer_ip,
        tls_version=tls_version,
    )


def _hold_until_signal() -> None:
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped.wait(3600):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HSL shared Vault pre-credential probe")
    parser.add_argument("--hold", action="store_true")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args(argv)
    vault_addr = os.environ.get("HSL_VAULT_ADDR", "")
    ca_file = os.environ.get("HSL_VAULT_CA_FILE", DEFAULT_CA_FILE)
    try:
        record = probe_once(vault_addr, ca_file, timeout_seconds=args.timeout)
    except ProbeError as exc:
        print(f"PRE_SECRET_ZERO_NETWORK_FAIL code={exc.code}", file=sys.stderr, flush=True)
        return 2
    print(
        "PRE_SECRET_ZERO_NETWORK_READY "
        + json.dumps(record, sort_keys=True, separators=(",", ":")),
        flush=True,
    )
    if args.hold:
        _hold_until_signal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
