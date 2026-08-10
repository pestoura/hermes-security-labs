"""Hermes-side TB1 authorization receipt issuance boundary.

Hermes is the sole execution-authorization authority. This module turns one
already-authorized typed effect into the exact signed receipt consumed by the
existing execution-plane verifier.

The issuer deliberately does not load, store or discover private keys. Signing
is delegated to an injected purpose-bound signer so production deployments can
use an HSM, KMS, Vault transit engine or another controlled signing service.

Repository/runtime separation is explicit: importing or instantiating this
module grants no authority and performs no I/O, dispatch or target interaction.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = ROOT / "platform" / "authorization-contract"
GATEWAY_CONTRACT_PATH = ROOT / "platform" / "gateway-protocol" / "gateway_protocol.py"


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical contract {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


authorization_contract = _load_module(
    "tb1_authorization_receipt_issuer_contract",
    AUTH_DIR / "authorization_receipt.py",
)
gateway_contract = _load_module(
    "tb1_authorization_issuer_gateway_contract",
    GATEWAY_CONTRACT_PATH,
)

DEFAULT_TTL_SECONDS = 300
SUPPORTED_ALGORITHMS = frozenset({"Ed25519", "ECDSA-P256-SHA256"})
SUPPORTED_INTRUSIVENESS = frozenset({"L0", "L1", "L2", "L3", "L4"})
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_EFFECT_FIELDS = frozenset(
    {
        "campaign_id",
        "run_id",
        "step_id",
        "roe_contract_id",
        "roe_contract_payload_sha256",
        "roe_step_request_id",
        "operation_id",
        "operation_version",
        "operation_parameters",
        "capability_id",
        "target",
        "intrusiveness_level",
    }
)
_UUID_FIELDS = ("campaign_id", "run_id", "step_id")


class AuthorizationIssuanceError(ValueError):
    """Fail-closed issuance error carrying a stable decision code."""

    @property
    def decision_code(self) -> str:
        return str(self)


class ReceiptSigner(Protocol):
    """Purpose-bound external signing boundary.

    Implementations own key access and key lifecycle. The issuer receives only
    the public key identifier, algorithm name and a signing operation.
    """

    key_id: str
    algorithm: str

    def sign(self, payload: bytes) -> bytes:
        ...


@dataclass(frozen=True)
class IssuedAuthorization:
    """Operational result with log-safe metadata and restricted receipt payload."""

    authorization_id: str
    authorization_ref: str
    key_id: str
    algorithm: str
    issued_at: str
    expires_at: str
    receipt: dict[str, Any] = field(repr=False)

    def sanitized_summary(self) -> dict[str, str]:
        return {
            "authorization_id": self.authorization_id,
            "authorization_ref": self.authorization_ref,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


def _utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _required_text(effect: Mapping[str, Any], field_name: str, *, limit: int) -> str:
    value = effect.get(field_name)
    if not isinstance(value, str) or not value or len(value) > limit:
        raise AuthorizationIssuanceError("ISSUER_EFFECT_INVALID")
    return value


def _validate_uuid(value: str) -> None:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise AuthorizationIssuanceError("ISSUER_EFFECT_UUID_INVALID") from exc
    if str(parsed) != value.lower():
        raise AuthorizationIssuanceError("ISSUER_EFFECT_UUID_INVALID")


def _validate_effect(effect: Mapping[str, Any]) -> None:
    if not isinstance(effect, Mapping):
        raise AuthorizationIssuanceError("ISSUER_EFFECT_REQUIRED")
    if set(effect) != _EFFECT_FIELDS:
        raise AuthorizationIssuanceError("ISSUER_EFFECT_FIELDS_INVALID")

    for field_name in _UUID_FIELDS:
        _validate_uuid(_required_text(effect, field_name, limit=36))

    _required_text(effect, "roe_contract_id", limit=128)
    _required_text(effect, "roe_step_request_id", limit=128)
    _required_text(effect, "operation_id", limit=128)
    _required_text(effect, "operation_version", limit=32)
    _required_text(effect, "capability_id", limit=128)

    roe_digest = effect.get("roe_contract_payload_sha256")
    if not isinstance(roe_digest, str) or _DIGEST.fullmatch(roe_digest) is None:
        raise AuthorizationIssuanceError("ISSUER_ROE_DIGEST_INVALID")

    intrusiveness = effect.get("intrusiveness_level")
    if intrusiveness not in SUPPORTED_INTRUSIVENESS:
        raise AuthorizationIssuanceError("ISSUER_INTRUSIVENESS_INVALID")

    if not isinstance(effect.get("operation_parameters"), Mapping):
        raise AuthorizationIssuanceError("ISSUER_PARAMETERS_INVALID")
    if not isinstance(effect.get("target"), Mapping):
        raise AuthorizationIssuanceError("ISSUER_TARGET_INVALID")


def _validate_signer(signer: ReceiptSigner) -> tuple[str, str]:
    key_id = getattr(signer, "key_id", None)
    algorithm = getattr(signer, "algorithm", None)
    if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None:
        raise AuthorizationIssuanceError("ISSUER_SIGNER_KEY_ID_INVALID")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise AuthorizationIssuanceError("ISSUER_SIGNER_ALGORITHM_UNSUPPORTED")
    sign = getattr(signer, "sign", None)
    if not callable(sign):
        raise AuthorizationIssuanceError("ISSUER_SIGNER_INVALID")
    return key_id, str(algorithm)


def _validate_ttl(ttl_seconds: int) -> int:
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise AuthorizationIssuanceError("ISSUER_TTL_INVALID")
    if not 1 <= ttl_seconds <= authorization_contract.MAX_RECEIPT_LIFETIME_SECONDS:
        raise AuthorizationIssuanceError("ISSUER_TTL_INVALID")
    return ttl_seconds


def _validate_built_receipt(receipt: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(
            authorization_contract.RECEIPT_SCHEMA.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise AuthorizationIssuanceError("ISSUER_SCHEMA_UNAVAILABLE") from exc

    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    if list(validator.iter_errors(receipt)):
        raise AuthorizationIssuanceError("ISSUER_RECEIPT_SCHEMA_INVALID")
    if authorization_contract.build_authorization_ref(receipt) != receipt.get(
        "authorization_ref"
    ):
        raise AuthorizationIssuanceError("ISSUER_REFERENCE_INTEGRITY_FAILED")


def issue_authorization_receipt(
    effect: Mapping[str, Any],
    signer: ReceiptSigner,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> IssuedAuthorization:
    """Issue one signed TB1 receipt for an exact already-authorized effect.

    The caller cannot supply issuer identity, authorization ID/reference,
    timestamps, signature metadata or signature bytes. Target and typed
    operation parameters are consumed only to derive canonical digests and are
    never copied into the receipt.
    """

    _validate_effect(effect)
    ttl = _validate_ttl(ttl_seconds)
    key_id, algorithm = _validate_signer(signer)

    try:
        parameter_digest = authorization_contract.canonical_parameters_sha256(
            effect["operation_parameters"]
        )
    except Exception as exc:  # noqa: BLE001 - malformed typed input fails closed
        raise AuthorizationIssuanceError("ISSUER_PARAMETERS_INVALID") from exc
    try:
        target_digest = gateway_contract.canonical_target_digest(effect["target"])
    except Exception as exc:  # noqa: BLE001 - malformed target fails closed
        raise AuthorizationIssuanceError("ISSUER_TARGET_INVALID") from exc

    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + timedelta(seconds=ttl)
    authorization_id = str(uuid.uuid4())

    receipt: dict[str, Any] = {
        "schema_version": authorization_contract.SCHEMA_VERSION,
        "domain": authorization_contract.DOMAIN,
        "issuer": authorization_contract.ISSUER,
        "authorization_id": authorization_id,
        "issued_at": _utc(now),
        "expires_at": _utc(expires),
        "campaign_id": str(effect["campaign_id"]),
        "run_id": str(effect["run_id"]),
        "step_id": str(effect["step_id"]),
        "roe_contract_id": str(effect["roe_contract_id"]),
        "roe_contract_payload_sha256": str(effect["roe_contract_payload_sha256"]),
        "roe_step_request_id": str(effect["roe_step_request_id"]),
        "operation_id": str(effect["operation_id"]),
        "operation_version": str(effect["operation_version"]),
        "operation_parameters_sha256": parameter_digest,
        "capability_id": str(effect["capability_id"]),
        "target_sha256": target_digest,
        "intrusiveness_level": str(effect["intrusiveness_level"]),
    }
    receipt["authorization_ref"] = authorization_contract.build_authorization_ref(
        receipt
    )

    payload = authorization_contract.canonical_signed_payload(receipt)
    try:
        raw_signature = signer.sign(payload)
    except Exception as exc:  # noqa: BLE001 - signer details are not exposed
        raise AuthorizationIssuanceError("ISSUER_SIGNING_FAILED") from exc
    if not isinstance(raw_signature, bytes) or not raw_signature:
        raise AuthorizationIssuanceError("ISSUER_SIGNATURE_INVALID")

    signature_value = base64.b64encode(raw_signature).decode("ascii")
    if len(signature_value) > 4096:
        raise AuthorizationIssuanceError("ISSUER_SIGNATURE_INVALID")
    receipt["signature"] = {
        "algorithm": algorithm,
        "key_id": key_id,
        "value": signature_value,
    }

    _validate_built_receipt(receipt)
    return IssuedAuthorization(
        authorization_id=authorization_id,
        authorization_ref=str(receipt["authorization_ref"]),
        key_id=key_id,
        algorithm=algorithm,
        issued_at=str(receipt["issued_at"]),
        expires_at=str(receipt["expires_at"]),
        receipt=receipt,
    )
