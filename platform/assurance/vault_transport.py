#!/usr/bin/env python3
"""Bounded HTTPS/JSON transport for the LAB_L1 Vault signer adapter.

This module is intentionally small. It exposes only GET/POST JSON requests to an
already-provisioned Vault API over certificate-verified HTTPS. It contains no Vault
administration, retry policy, credential persistence, logging or secret material.
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Protocol

_MAX_RESPONSE_BYTES = 262_144
_MAX_HEADER_VALUE = 8_192
_ALLOWED_METHODS = frozenset({"GET", "POST"})
_ALLOWED_HEADERS = frozenset({"X-Vault-Token", "X-Vault-Namespace"})


class VaultTransportError(RuntimeError):
    """Stable, secret-free transport failure."""

    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        suffix = f" status={status_code}" if status_code is not None else ""
        super().__init__(f"{code}{suffix}")


@dataclass(frozen=True)
class VaultHttpResponse:
    status_code: int
    body: Mapping[str, object]
    request_id: str | None


class VaultTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> VaultHttpResponse:
        ...


def _has_controls(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _validate_base_url(vault_addr: object) -> str:
    if not isinstance(vault_addr, str) or not vault_addr or len(vault_addr) > 2_048:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    if _has_controls(vault_addr):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")

    try:
        parsed = urllib.parse.urlsplit(vault_addr)
    except ValueError as exc:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID") from exc

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")

    try:
        _ = parsed.port
    except ValueError as exc:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID") from exc

    return vault_addr.rstrip("/")


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    timeout = float(value)
    if timeout < 0.25 or timeout > 30.0:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    return timeout


def _validate_path(path: object) -> str:
    if not isinstance(path, str) or not path.startswith("/v1/") or len(path) > 2_048:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    if _has_controls(path):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")

    parsed = urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")

    decoded_path = urllib.parse.unquote(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    if not decoded_path.startswith("/v1/"):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
    return parsed.path


def _validate_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")

    validated: dict[str, str] = {}
    for name, value in headers.items():
        if name not in _ALLOWED_HEADERS:
            raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
        if (
            not isinstance(value, str)
            or not value
            or len(value) > _MAX_HEADER_VALUE
            or _has_controls(value)
        ):
            raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
        validated[name] = value
    return validated


class UrllibVaultTransport:
    """Certificate-verifying standard-library Vault transport."""

    def __init__(
        self,
        vault_addr: str,
        *,
        timeout_seconds: float = 3.0,
        ca_bundle_path: str | None = None,
    ) -> None:
        self._vault_addr = _validate_base_url(vault_addr)
        self._timeout_seconds = _validate_timeout(timeout_seconds)
        if ca_bundle_path is not None:
            if (
                not isinstance(ca_bundle_path, str)
                or not ca_bundle_path
                or len(ca_bundle_path) > 1_024
                or _has_controls(ca_bundle_path)
            ):
                raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
        self._ssl_context = ssl.create_default_context(cafile=ca_bundle_path)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> VaultHttpResponse:
        if not isinstance(method, str) or method not in _ALLOWED_METHODS:
            raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
        validated_path = _validate_path(path)
        validated_headers = _validate_headers(headers)

        data: bytes | None = None
        if json_body is not None:
            if method != "POST" or not isinstance(json_body, Mapping):
                raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID")
            try:
                data = json.dumps(
                    dict(json_body),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise VaultTransportError("VAULT_TRANSPORT_REQUEST_INVALID") from exc

        request_headers = {"Accept": "application/json", **validated_headers}
        if data is not None:
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self._vault_addr + validated_path,
            data=data,
            headers=request_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout_seconds,
                context=self._ssl_context,
            ) as response:
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(payload) > _MAX_RESPONSE_BYTES:
                    raise VaultTransportError("VAULT_TRANSPORT_RESPONSE_TOO_LARGE")
                try:
                    decoded = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise VaultTransportError("VAULT_TRANSPORT_RESPONSE_INVALID") from exc
                if not isinstance(decoded, dict):
                    raise VaultTransportError("VAULT_TRANSPORT_RESPONSE_INVALID")
                response_headers = getattr(response, "headers", {})
                request_id = None
                if hasattr(response_headers, "get"):
                    candidate = response_headers.get("X-Vault-Request")
                    if (
                        isinstance(candidate, str)
                        and candidate
                        and len(candidate) <= 256
                        and not _has_controls(candidate)
                    ):
                        request_id = candidate
                return VaultHttpResponse(
                    status_code=int(getattr(response, "status", 200)),
                    body=decoded,
                    request_id=request_id,
                )
        except VaultTransportError:
            raise
        except urllib.error.HTTPError as exc:
            raise VaultTransportError(
                "VAULT_TRANSPORT_HTTP_ERROR", status_code=int(exc.code)
            ) from None
        except ssl.SSLError:
            raise VaultTransportError("VAULT_TRANSPORT_TLS_FAILED") from None
        except (TimeoutError, socket.timeout):
            raise VaultTransportError("VAULT_TRANSPORT_TIMEOUT") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), ssl.SSLError):
                raise VaultTransportError("VAULT_TRANSPORT_TLS_FAILED") from None
            if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                raise VaultTransportError("VAULT_TRANSPORT_TIMEOUT") from None
            raise VaultTransportError("VAULT_TRANSPORT_UNREACHABLE") from None
        except OSError:
            raise VaultTransportError("VAULT_TRANSPORT_UNREACHABLE") from None
