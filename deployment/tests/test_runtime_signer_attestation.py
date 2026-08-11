from __future__ import annotations

import copy
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deployment" / "runtime-promotion" / "runtime_signer_attestation.py"
DEPLOYMENT_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "tb1-authorization-deployment-descriptor.example.yaml"
)
ATTESTATION_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "tb1-signer-attestation.example.yaml"
)
SOURCE_SHA = "4" * 64
SOURCE_REF = "evidence://runner-live/signer/provider-metadata/fixture.json"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


signer = _load("runtime_signer_attestation_test", MODULE_PATH)


def _deployment() -> dict[str, Any]:
    document = yaml.safe_load(DEPLOYMENT_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _approved_sha() -> str:
    return signer._approved_public_key_digest(_deployment())


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _observed_attestation() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "observation_status": "OBSERVED",
        "attestation_id": "tb1-signer-observation-fixture",
        "observation_source": "provider-read-only-metadata",
        "observed_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=10)),
        "source_evidence_ref": SOURCE_REF,
        "source_evidence_sha256": SOURCE_SHA,
        "provider_kind": "HSM",
        "provider_ref": "tb1-authorizer-example-slot-a",
        "key_id": "tb1-authorization-example-ed25519",
        "algorithm": "Ed25519",
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "public_key_spki_sha256": _approved_sha(),
    }


class StaticEvidenceVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str]] = []

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        self.calls.append((evidence_ref, sha256))
        return self.accepted and evidence_ref == SOURCE_REF and sha256 == SOURCE_SHA


def test_committed_example_is_inert_and_cannot_pass() -> None:
    deployment = signer.load_deployment_descriptor(DEPLOYMENT_PATH)
    attestation = signer.load_attestation(ATTESTATION_PATH)
    result = signer.verify_signer_attestation(
        deployment,
        attestation,
        evidence_verifier=StaticEvidenceVerifier(),
    )
    assert result.signer_attestation_checks_passed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert "external signer provider observation has not run" in result.findings


def test_fresh_custodied_observation_matches_approved_signer() -> None:
    verifier = StaticEvidenceVerifier()
    result = signer.verify_signer_attestation(
        _deployment(),
        _observed_attestation(),
        evidence_verifier=verifier,
    )
    assert result.signer_attestation_checks_passed is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert result.public_key_spki_sha256 == _approved_sha()
    assert result.source_evidence_verified is True
    assert verifier.calls == [(SOURCE_REF, SOURCE_SHA)]


def test_default_evidence_verifier_refuses_observed_envelope() -> None:
    result = signer.verify_signer_attestation(_deployment(), _observed_attestation())
    assert result.signer_attestation_checks_passed is False
    assert result.source_evidence_verified is False
    assert "source provider observation evidence is not verified" in result.findings


def test_provider_binding_mismatch_fails_closed() -> None:
    attestation = _observed_attestation()
    attestation["provider_ref"] = "different-provider-slot"
    result = signer.verify_signer_attestation(
        _deployment(), attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.signer_attestation_checks_passed is False
    assert any("provider_ref" in item for item in result.findings)


def test_public_key_fingerprint_mismatch_fails_closed() -> None:
    attestation = _observed_attestation()
    attestation["public_key_spki_sha256"] = "5" * 64
    result = signer.verify_signer_attestation(
        _deployment(), attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.signer_attestation_checks_passed is False
    assert any("public-key fingerprint" in item for item in result.findings)


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("key_state", "disabled", "not active"),
        ("signing_enabled", False, "not enabled for signing"),
        ("private_key_exportable", True, "exportable"),
    ],
)
def test_provider_protection_state_must_be_acceptable(
    field: str, value: Any, needle: str
) -> None:
    attestation = _observed_attestation()
    attestation[field] = value
    result = signer.verify_signer_attestation(
        _deployment(), attestation, evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.signer_attestation_checks_passed is False
    assert any(needle in item for item in result.findings)


def test_stale_and_future_observations_fail_closed() -> None:
    stale = _observed_attestation()
    stale["observed_at"] = _iso(datetime.now(timezone.utc) - timedelta(minutes=6))
    stale_result = signer.verify_signer_attestation(
        _deployment(), stale, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("stale" in item for item in stale_result.findings)

    future = _observed_attestation()
    future["observed_at"] = _iso(datetime.now(timezone.utc) + timedelta(minutes=1))
    future_result = signer.verify_signer_attestation(
        _deployment(), future, evidence_verifier=StaticEvidenceVerifier()
    )
    assert any("future" in item for item in future_result.findings)


def test_source_evidence_must_be_verified() -> None:
    verifier = StaticEvidenceVerifier(accepted=False)
    result = signer.verify_signer_attestation(
        _deployment(), _observed_attestation(), evidence_verifier=verifier
    )
    assert result.signer_attestation_checks_passed is False
    assert result.source_evidence_verified is False


def test_secret_bearing_attestation_is_refused_before_verification() -> None:
    attestation = _observed_attestation()
    attestation["private_key"] = "forbidden"
    with pytest.raises(signer.SignerAttestationError) as exc:
        signer.verify_signer_attestation(
            _deployment(), attestation, evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code in {"ATTESTATION_INVALID", "ATTESTATION_SECRET_MATERIAL_REFUSED"}


def test_tampered_deployment_descriptor_is_refused() -> None:
    deployment = copy.deepcopy(_deployment())
    deployment["signer"]["algorithm"] = "ECDSA-P256-SHA256"
    with pytest.raises(signer.SignerAttestationError) as exc:
        signer.verify_signer_attestation(
            deployment,
            _observed_attestation(),
            evidence_verifier=StaticEvidenceVerifier(),
        )
    assert exc.value.code == "DEPLOYMENT_DESCRIPTOR_INVALID"


def test_safe_result_contains_no_private_or_raw_provider_material() -> None:
    result = signer.verify_signer_attestation(
        _deployment(),
        _observed_attestation(),
        evidence_verifier=StaticEvidenceVerifier(),
    )
    rendered = repr(result.as_dict()).lower()
    for forbidden in ("private_key", "secret", "credential", "provider_response"):
        assert forbidden not in rendered


def test_source_has_no_provider_client_network_or_private_key_loader() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "boto3",
        "hvac",
        "pkcs11",
        "requests",
        "http.client",
        "socket",
        "subprocess",
        "load_pem_private_key",
        "load_der_private_key",
        "private_bytes",
        ".sign(",
    ):
        assert forbidden not in source
    assert "DenyAllEvidenceVerifier" in source
    assert "promotion_allowed=False" in source
