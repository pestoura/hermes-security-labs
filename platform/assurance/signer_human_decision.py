#!/usr/bin/env python3
"""Repository-only human signer-decision contract.

This module records and validates the explicit human supplier-class decision that
CHG-HSL-061 requires before any transition away from signer NO_SELECTION.

It deliberately does NOT:
- select a signer class automatically;
- verify provider evidence itself;
- create/import keys or trust material;
- install a trust store;
- invoke a provider, network, process, systemd or runtime path;
- grant execution or promotion authority.

An APPROVED record only binds the human choice to explicit evidence references and
SHA-256 digests. The referenced evidence must still be verified by the existing
canonical signer/trust/promotion gates before a later transition can be accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "signer-human-decision.schema.json"
DECISION_PATH = ROOT / "assurance" / "signer-human-decision.yaml"

NO_DECISION = "NO_DECISION"
APPROVED = "APPROVED"
SELECTABLE_CLASSES = ("KMS", "HSM", "VAULT")
REQUIRED_EVIDENCE_KINDS = frozenset(
    {
        "capability_evidence",
        "signer_attestation",
        "trust_store_manifest",
        "r1_r8_review",
    }
)

_FORBIDDEN_RUNTIME_IMPORTS = {
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "boto3",
    "hvac",
    "pkcs11",
    "os",
    "shutil",
}


class SignerHumanDecisionError(ValueError):
    """Fail-closed signer human-decision contract violation."""


@dataclass(frozen=True)
class SignerHumanDecisionEvaluation:
    state: str
    decision_id: str | None
    selected_class: str | None
    evidence_refs_complete: bool
    promotion_allowed: bool
    runtime_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "decision_id": self.decision_id,
            "selected_class": self.selected_class,
            "evidence_refs_complete": self.evidence_refs_complete,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
        }


def load_decision_schema() -> dict[str, Any]:
    document = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):  # pragma: no cover - repository defect
        raise SignerHumanDecisionError("signer human-decision schema must be an object")
    return document


def load_decision(path: Path = DECISION_PATH) -> dict[str, Any]:
    """Load and schema-validate one signer human-decision record."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SignerHumanDecisionError("signer human-decision document must be a mapping")

    schema = load_decision_schema()
    errors = sorted(
        jsonschema.Draft7Validator(schema).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise SignerHumanDecisionError(
            f"signer human-decision schema violation at {location}: {first.message}"
        )
    return document


def _validate_decided_at(value: Any) -> None:
    if not isinstance(value, str):
        raise SignerHumanDecisionError("APPROVED decision requires decided_at")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SignerHumanDecisionError("decided_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SignerHumanDecisionError("decided_at must include an explicit timezone")


def _validate_evidence_refs(entries: Any) -> None:
    if not isinstance(entries, list):
        raise SignerHumanDecisionError("evidence_refs must be a list")

    kinds: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise SignerHumanDecisionError("each evidence_ref must be a mapping")
        kinds.append(str(entry.get("kind")))

    duplicates = sorted({kind for kind in kinds if kinds.count(kind) > 1})
    if duplicates:
        raise SignerHumanDecisionError(
            "duplicate signer decision evidence kind(s): " + ", ".join(duplicates)
        )

    observed = set(kinds)
    missing = sorted(REQUIRED_EVIDENCE_KINDS - observed)
    extras = sorted(observed - REQUIRED_EVIDENCE_KINDS)
    if missing:
        raise SignerHumanDecisionError(
            "missing required signer decision evidence kind(s): " + ", ".join(missing)
        )
    if extras:
        raise SignerHumanDecisionError(
            "unexpected signer decision evidence kind(s): " + ", ".join(extras)
        )


def evaluate_human_decision(
    document: Mapping[str, Any] | None = None,
) -> SignerHumanDecisionEvaluation:
    """Evaluate the human-decision record without granting any runtime authority."""
    if document is None:
        document = load_decision()
    elif not isinstance(document, Mapping):
        raise SignerHumanDecisionError("signer human-decision document must be a mapping")
    else:
        schema = load_decision_schema()
        errors = sorted(
            jsonschema.Draft7Validator(schema).iter_errors(document),
            key=lambda error: list(error.path),
        )
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.path) or "<root>"
            raise SignerHumanDecisionError(
                f"signer human-decision schema violation at {location}: {first.message}"
            )

    decision = document.get("decision") or {}
    state = str(decision.get("state"))

    if state == NO_DECISION:
        return SignerHumanDecisionEvaluation(
            state=NO_DECISION,
            decision_id=None,
            selected_class=None,
            evidence_refs_complete=False,
            promotion_allowed=False,
            runtime_status="NOT_RUN",
        )

    if state != APPROVED:
        raise SignerHumanDecisionError(f"unsupported signer decision state: {state}")

    selected_class = str(decision.get("selected_class"))
    if selected_class not in SELECTABLE_CLASSES:
        raise SignerHumanDecisionError(
            f"selected signer class is not an approved custody class: {selected_class}"
        )

    _validate_decided_at(decision.get("decided_at"))
    _validate_evidence_refs(decision.get("evidence_refs"))

    return SignerHumanDecisionEvaluation(
        state=APPROVED,
        decision_id=str(decision.get("decision_id")),
        selected_class=selected_class,
        evidence_refs_complete=True,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
    )


def _module_has_no_provider_or_runtime_imports() -> bool:
    source = Path(__file__).read_text(encoding="utf-8")
    for forbidden in _FORBIDDEN_RUNTIME_IMPORTS:
        if f"import {forbidden}" in source or f"from {forbidden}" in source:
            return False
    for forbidden in (
        "write_text(",
        "write_bytes(",
        "unlink(",
        "chmod(",
        "load_pem_private_key",
        "load_der_private_key",
        "private_bytes",
        ".sign(",
        "promote(",
        "install_trust_store",
    ):
        if forbidden in source:
            return False
    return True
