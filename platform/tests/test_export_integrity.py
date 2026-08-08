from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/interoperability/export_integrity.py"
spec = importlib.util.spec_from_file_location("export_integrity", PATH)
assert spec and spec.loader
integrity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = integrity
spec.loader.exec_module(integrity)

PAYLOAD = {"document_type": "synthetic", "results": [{"finding": "synthetic"}]}


def _signature(payload=PAYLOAD):
    return {
        "verified": True,
        "signer": "synthetic-signer",
        "algorithm": "synthetic-algorithm",
        "payload_sha256": integrity.payload_sha256(payload),
    }


def test_signature_is_bound_to_exact_export_payload() -> None:
    assert integrity.validate_signature_binding(payload=PAYLOAD, signature_evidence=_signature()) == integrity.payload_sha256(PAYLOAD)


def test_signature_for_different_payload_is_rejected() -> None:
    with pytest.raises(integrity.ExportIntegrityError, match="SIGNATURE_PAYLOAD_DIGEST_MISMATCH"):
        integrity.validate_signature_binding(
            payload={**PAYLOAD, "document_type": "modified"},
            signature_evidence=_signature(),
        )


def test_verified_boolean_without_payload_binding_is_not_enough() -> None:
    signature = _signature()
    signature.pop("payload_sha256")
    with pytest.raises(integrity.ExportIntegrityError, match="SIGNATURE_PAYLOAD_DIGEST_REQUIRED"):
        integrity.validate_signature_binding(payload=PAYLOAD, signature_evidence=signature)
