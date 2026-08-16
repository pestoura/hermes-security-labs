#!/usr/bin/env python3
"""Fail-closed LAB_L1 Vault Transit Ed25519 signing adapter.

The adapter implements the existing provider-neutral SigningService boundary. It can
authenticate with an already-provisioned AppRole, observe one already-provisioned
Transit key and request a signature. It cannot create, rotate, export, delete or
configure keys, policies, auth methods or mounts. Credentials exist only in memory and
are never returned in public result/evidence metadata.

A structurally admissible SigningResult is not custody/trust/R1-R8 proof. Provider
attestation, EvidenceVerifier acceptance, trust binding and live promotion remain
separate governed gates.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_DIR = Path(__file__).resolve().parent
_SIGNING_PATH = _DIR / "signing_service.py"
_TRANSPORT_PATH = _DIR / "vault_transport.py"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_SECRET_VALUE = 8_192
_TRANSPORT_ERROR_CODES = frozenset(
    {
        "VAULT_TRANSPORT_REQUEST_INVALID",
        "VAULT_TRANSPORT_HTTP_ERROR",
        "VAULT_TRANSPORT_TLS_FAILED",
        "VAULT_TRANSPORT_TIMEOUT",
        "VAULT_TRANSPORT_UNREACHABLE",
        "VAULT_TRANSPORT_RESPONSE_TOO_LARGE",
        "VAULT_TRANSPORT_RESPONSE_INVALID",
    }
)


def _load_sibling(path: Path, module_name: str):
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file:
            try:
                if Path(module_file).resolve() == resolved:
                    return module
            except (OSError, RuntimeError):
                pass
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError("ASSURANCE_DEPENDENCY_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_signing = _load_sibling(_SIGNING_PATH, "hsl_vault_signer_signing_service")
_transport = _load_sibling(_TRANSPORT_PATH, "hsl_vault_signer_transport")


class VaultSignerError(ValueError):
    """Stable, secret-free provider adapter failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str:
        ...


def _has_controls(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _bounded_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 512
        and not _has_controls(value)
    )


def _valid_https_root(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 2_048 or _has_controls(value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )


def _signing_module_for_request(request: object):
    """Resolve the canonical signing module that defined this request object.

    Repository assurance tests intentionally load the same source file under isolated
    module names. Python class identity is module-specific, so reusing an arbitrary
    previously loaded copy would reject an otherwise canonical SigningRequest before
    provider logic runs. We preserve the strict isinstance contract by accepting only a
    class whose defining module points at the exact canonical signing_service.py path.
    """

    module_name = getattr(type(request), "__module__", "")
    module = sys.modules.get(module_name) if isinstance(module_name, str) else None
    module_file = getattr(module, "__file__", None)
    if module is not None and module_file:
        try:
            same_source = Path(module_file).resolve() == _SIGNING_PATH.resolve()
        except (OSError, RuntimeError):
            same_source = False
        request_type = getattr(module, "SigningRequest", None)
        if same_source and isinstance(request_type, type) and isinstance(request, request_type):
            return module

    if isinstance(request, _signing.SigningRequest):
        return _signing

    raise _signing.SigningServiceError(
        "SIGNING_REQUEST_INVALID", "request must be a SigningRequest"
    )


def _transport_failure(exc: BaseException) -> tuple[str, int | None] | None:
    """Recognize only the closed VaultTransport error protocol across module copies."""

    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status_code", None)
    if code not in _TRANSPORT_ERROR_CODES:
        return None
    if status_code is not None:
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            return None
        if status_code < 100 or status_code > 599:
            return None
    return str(code), status_code


@dataclass(frozen=True)
class VaultSignerConfig:
    vault_addr: str
    transit_mount: str
    key_name: str
    approle_mount: str
    role_id_ref: str
    secret_id_ref: str
    expected_algorithm: str = "Ed25519"
    namespace: str | None = None
    timeout_seconds: float = 3.0
    ca_bundle_path: str | None = None

    def __post_init__(self) -> None:
        if not _valid_https_root(self.vault_addr):
            raise VaultSignerError("VAULT_CONFIG_INVALID")
        for value in (self.transit_mount, self.key_name, self.approle_mount):
            if not isinstance(value, str) or _NAME_RE.fullmatch(value) is None:
                raise VaultSignerError("VAULT_CONFIG_INVALID")
        if not _bounded_reference(self.role_id_ref) or not _bounded_reference(self.secret_id_ref):
            raise VaultSignerError("VAULT_CONFIG_INVALID")
        if self.expected_algorithm != "Ed25519":
            raise VaultSignerError("VAULT_CONFIG_INVALID")
        if self.namespace is not None:
            if (
                not isinstance(self.namespace, str)
                or not self.namespace
                or len(self.namespace) > 256
                or _has_controls(self.namespace)
            ):
                raise VaultSignerError("VAULT_CONFIG_INVALID")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or float(self.timeout_seconds) < 0.25
            or float(self.timeout_seconds) > 30.0
        ):
            raise VaultSignerError("VAULT_CONFIG_INVALID")
        if self.ca_bundle_path is not None:
            if (
                not isinstance(self.ca_bundle_path, str)
                or not self.ca_bundle_path
                or len(self.ca_bundle_path) > 1_024
                or _has_controls(self.ca_bundle_path)
            ):
                raise VaultSignerError("VAULT_CONFIG_INVALID")


@dataclass(frozen=True)
class VaultKeyObservation:
    key_name: str
    key_version: int
    vault_type: str
    algorithm: str
    public_key_spki_sha256: str
    exportable: bool
    allow_plaintext_backup: bool
    supports_signing: bool


class VaultAuthSession:
    """Bounded AppRole token lifecycle with in-memory token caching only."""

    def __init__(
        self,
        config: VaultSignerConfig,
        *,
        transport: object,
        secret_resolver: SecretResolver,
    ) -> None:
        self._config = config
        self._transport = transport
        self._secret_resolver = secret_resolver
        self._token: str | None = None

    def invalidate(self) -> None:
        self._token = None

    def token(self) -> str:
        if self._token is not None:
            return self._token
        try:
            role_id = self._secret_resolver.resolve(self._config.role_id_ref)
            secret_id = self._secret_resolver.resolve(self._config.secret_id_ref)
        except Exception:
            raise VaultSignerError("VAULT_SECRET_RESOLUTION_FAILED") from None
        for value in (role_id, secret_id):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > _MAX_SECRET_VALUE
                or _has_controls(value)
            ):
                raise VaultSignerError("VAULT_SECRET_RESOLUTION_FAILED")

        headers = _namespace_headers(self._config)
        try:
            response = self._transport.request(
                "POST",
                f"/v1/auth/{self._config.approle_mount}/login",
                headers=headers,
                json_body={"role_id": role_id, "secret_id": secret_id},
            )
        except Exception as exc:
            if _transport_failure(exc) is None:
                raise
            raise VaultSignerError("VAULT_AUTH_FAILED") from None

        body = getattr(response, "body", None)
        if not isinstance(body, Mapping):
            raise VaultSignerError("VAULT_AUTH_FAILED")
        auth = body.get("auth")
        if not isinstance(auth, Mapping):
            raise VaultSignerError("VAULT_AUTH_FAILED")
        token = auth.get("client_token")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > _MAX_SECRET_VALUE
            or _has_controls(token)
        ):
            raise VaultSignerError("VAULT_AUTH_FAILED")
        self._token = token
        return token


def _namespace_headers(config: VaultSignerConfig) -> dict[str, str]:
    if config.namespace is None:
        return {}
    return {"X-Vault-Namespace": config.namespace}


def _authenticated_headers(config: VaultSignerConfig, token: str) -> dict[str, str]:
    return {"X-Vault-Token": token, **_namespace_headers(config)}


class VaultSignerAdapter:
    """Vault Transit Ed25519 implementation of the provider-neutral signing boundary."""

    def __init__(
        self,
        config: VaultSignerConfig,
        *,
        transport: object | None = None,
        secret_resolver: SecretResolver,
    ) -> None:
        if not isinstance(config, VaultSignerConfig):
            raise VaultSignerError("VAULT_CONFIG_INVALID")
        self._config = config
        self._transport = transport or _transport.UrllibVaultTransport(
            config.vault_addr,
            timeout_seconds=float(config.timeout_seconds),
            ca_bundle_path=config.ca_bundle_path,
        )
        self._auth = VaultAuthSession(
            config,
            transport=self._transport,
            secret_resolver=secret_resolver,
        )

    def _authenticated_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
    ):
        token = self._auth.token()
        try:
            return self._transport.request(
                method,
                path,
                headers=_authenticated_headers(self._config, token),
                json_body=json_body,
            )
        except Exception as first_exc:
            first_failure = _transport_failure(first_exc)
            if first_failure is None:
                raise
            code, status = first_failure
            if code == "VAULT_TRANSPORT_HTTP_ERROR" and status in {401, 403}:
                self._auth.invalidate()
                retry_token = self._auth.token()
                try:
                    return self._transport.request(
                        method,
                        path,
                        headers=_authenticated_headers(self._config, retry_token),
                        json_body=json_body,
                    )
                except Exception as retry_exc:
                    retry_failure = _transport_failure(retry_exc)
                    if retry_failure is None:
                        raise
                    retry_code, retry_status = retry_failure
                    if retry_code == "VAULT_TRANSPORT_HTTP_ERROR" and retry_status in {401, 403}:
                        raise VaultSignerError("VAULT_ACCESS_DENIED") from None
                    raise VaultSignerError("VAULT_UNAVAILABLE") from None
            raise VaultSignerError("VAULT_UNAVAILABLE") from None

    def _observe_key(self) -> VaultKeyObservation:
        response = self._authenticated_request(
            "GET", f"/v1/{self._config.transit_mount}/keys/{self._config.key_name}"
        )
        body = getattr(response, "body", None)
        if not isinstance(body, Mapping):
            raise VaultSignerError("VAULT_KEY_OBSERVATION_FAILED")
        data = body.get("data")
        if not isinstance(data, Mapping):
            raise VaultSignerError("VAULT_KEY_OBSERVATION_FAILED")

        if (
            data.get("name") != self._config.key_name
            or data.get("type") != "ed25519"
            or data.get("supports_signing") is not True
            or data.get("derived") is not False
            or data.get("exportable") is not False
            or data.get("allow_plaintext_backup") is not False
        ):
            raise VaultSignerError("VAULT_KEY_NOT_ADMISSIBLE")

        keys = data.get("keys")
        if not isinstance(keys, Mapping) or not keys:
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID")
        versions: list[int] = []
        for raw_version in keys:
            if not isinstance(raw_version, str) or not raw_version.isdigit():
                continue
            version = int(raw_version)
            if version > 0:
                versions.append(version)
        if not versions:
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID")
        key_version = max(versions)
        key_entry = keys.get(str(key_version))
        if not isinstance(key_entry, Mapping):
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID")
        public_key_pem = key_entry.get("public_key")
        if not isinstance(public_key_pem, str) or not public_key_pem or len(public_key_pem) > 8_192:
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID")
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError):
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID") from None
        if not isinstance(public_key, Ed25519PublicKey):
            raise VaultSignerError("VAULT_KEY_IDENTITY_INVALID")
        public_der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return VaultKeyObservation(
            key_name=self._config.key_name,
            key_version=key_version,
            vault_type="ed25519",
            algorithm="Ed25519",
            public_key_spki_sha256=hashlib.sha256(public_der).hexdigest(),
            exportable=False,
            allow_plaintext_backup=False,
            supports_signing=True,
        )

    def sign(self, request):
        signing = _signing_module_for_request(request)
        request = signing.validate_signing_request(request)
        observation = self._observe_key()
        payload = signing.canonical_signing_payload(request)
        response = self._authenticated_request(
            "POST",
            f"/v1/{self._config.transit_mount}/sign/{self._config.key_name}",
            json_body={
                "input": base64.b64encode(payload).decode("ascii"),
                "key_version": observation.key_version,
            },
        )
        signature = self._parse_signature(response, observation.key_version)
        audit_ref = self._build_audit_ref(request, observation, signature)
        result = signing.SigningResult(
            signature_b64=base64.b64encode(signature).decode("ascii"),
            key_id=(
                f"vault:{self._config.transit_mount}:{self._config.key_name}:"
                f"v{observation.key_version}"
            ),
            algorithm="Ed25519",
            public_key_spki_sha256=observation.public_key_spki_sha256,
            signer_class="VAULT",
            authority="EXTERNAL_CUSTODY",
            admissible_for_lab_l1=True,
            audit_ref=audit_ref,
        )
        return signing.require_lab_l1_admissible(result)

    @staticmethod
    def _parse_signature(response: object, expected_version: int) -> bytes:
        body = getattr(response, "body", None)
        if not isinstance(body, Mapping):
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        data = body.get("data")
        if not isinstance(data, Mapping):
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        provider_signature = data.get("signature")
        if not isinstance(provider_signature, str) or len(provider_signature) > 16_384:
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        parts = provider_signature.split(":", 2)
        if len(parts) != 3 or parts[0] != "vault" or not parts[1].startswith("v"):
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        raw_version = parts[1][1:]
        if not raw_version.isdigit() or int(raw_version) <= 0:
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        if int(raw_version) != expected_version:
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        try:
            signature = base64.b64decode(parts[2], validate=True)
        except (ValueError, TypeError):
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID") from None
        if len(signature) != 64:
            raise VaultSignerError("VAULT_SIGN_RESPONSE_INVALID")
        return signature

    @staticmethod
    def _build_audit_ref(request, observation: VaultKeyObservation, signature: bytes) -> str:
        public_record = {
            "schema_version": "vault-sign-operation/v1",
            "provider": "vault-transit",
            "key_name": observation.key_name,
            "key_version": observation.key_version,
            "algorithm": observation.algorithm,
            "public_key_spki_sha256": observation.public_key_spki_sha256,
            "request_digest_sha256": request.digest_sha256,
            "purpose": request.purpose,
            "domain": request.domain,
            "correlation_id": request.correlation_id,
            "signature_sha256": hashlib.sha256(signature).hexdigest(),
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "execution_authority": "NONE",
        }
        try:
            canonical = json.dumps(
                public_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise VaultSignerError("VAULT_AUDIT_IDENTITY_FAILED") from None
        return f"evidence://vault-sign-operation/{hashlib.sha256(canonical).hexdigest()}"
