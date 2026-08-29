#!/usr/bin/env python3
"""Tests for the shared-Vault signer decision evidence bundle."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = ROOT / "deployment/shared-vault-hsl/signer-evidence/vault_provider_observation.py"
ASSEMBLER = ROOT / "deployment/shared-vault-hsl/signer-evidence/signer_decision_evidence.py"
BUNDLE_SCHEMA = ROOT / "deployment/shared-vault-hsl/signer-evidence/decision-evidence-bundle.schema.json"
TRUST_SCHEMA = ROOT / "platform/schemas/signer-trust-manifest.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _public_key_pem() -> str:
    key = Ed25519PrivateKey.from_private_bytes(b"\xa2" * 32).public_key()
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _raw_key_response() -> dict:
    return {
        "data": {
            "name": "hsl-signing",
            "type": "ed25519",
            "supports_signing": True,
            "derived": False,
            "exportable": False,
            "allow_plaintext_backup": False,
            "keys": {"7": {"public_key": _public_key_pem()}},
        }
    }


def _checks() -> dict[str, bool]:
    return {
        "key_read_passed": True,
        "sign_verify_passed": True,
        "negative_sys_passed": True,
        "negative_auth_passed": True,
        "audit_attribution_passed": True,
        "no_secret_material_persisted": True,
    }


def _observation(observed_at: str | None = None) -> dict:
    provider = _load("hsl_provider_for_bundle_test", PROVIDER)
    return provider.normalize_provider_observation(
        _raw_key_response(),
        observed_at=observed_at or _now(),
        capability_checks=_checks(),
        bootstrap_evidence={
            "ref": "evidence://signer/secret-zero-observed-pass.json",
            "sha256": "a" * 64,
        },
        audit_evidence={
            "ref": "evidence://signer/vault-sign-audit-attribution.json",
            "sha256": "b" * 64,
        },
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_bundle_is_ready_but_grants_no_authority(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_test", ASSEMBLER)
    bundle = module.assemble_decision_evidence(
        _observation(), output_dir=tmp_path, evaluated_at=_now()
    )
    assert bundle["state"] == "READY_FOR_HUMAN_DECISION"
    assert bundle["custody_class"] == "VAULT"
    assert bundle["signer_decision_effect"] == "NONE"
    assert bundle["supplier_selection_effect"] == "NONE"
    assert bundle["trust_binding_allowed"] is False
    assert bundle["promotion_allowed"] is False
    assert bundle["execution_authority"] == "NONE"
    assert bundle["runtime_status"] == "NOT_RUN"
    kinds = {item["kind"] for item in bundle["decision_evidence_refs"]}
    assert kinds == {
        "capability_evidence",
        "signer_attestation",
        "trust_store_manifest",
        "r1_r8_review",
    }
    assert module.verify_decision_evidence_bundle(bundle, tmp_path) is True

    schema = _read_json(BUNDLE_SCHEMA)
    jsonschema.Draft202012Validator(schema).validate(bundle)


def test_generated_attestation_and_trust_manifest_are_canonical(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_canonical_test", ASSEMBLER)
    bundle = module.assemble_decision_evidence(
        _observation(), output_dir=tmp_path, evaluated_at=_now()
    )
    attestation = _read_json(tmp_path / bundle["artifacts"]["signer_attestation"]["file"])
    trust_manifest = _read_json(tmp_path / bundle["artifacts"]["trust_store_manifest"]["file"])
    public_store = _read_json(tmp_path / bundle["artifacts"]["public_trust_store"]["file"])

    assert attestation["observation_status"] == "OBSERVED"
    assert attestation["provider_kind"] == "VAULT"
    assert attestation["provider_ref"] == "https://hermes-vault:8200/hsl-transit/hsl-signing"
    assert attestation["key_id"] == "vault:hsl-transit:hsl-signing:v7"
    assert attestation["private_key_exportable"] is False
    assert public_store["keys"][0]["key_id"] == attestation["key_id"]
    assert public_store["keys"][0]["public_key"]

    trust_schema = _read_json(TRUST_SCHEMA)
    jsonschema.Draft7Validator(trust_schema).validate(trust_manifest)
    assert trust_manifest["public_key_spki_sha256"] == attestation["public_key_spki_sha256"]
    assert trust_manifest["trust_binding_allowed"] is False


def test_r1_r8_review_contains_exactly_eight_passes(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_r1r8_test", ASSEMBLER)
    bundle = module.assemble_decision_evidence(
        _observation(), output_dir=tmp_path, evaluated_at=_now()
    )
    review = _read_json(tmp_path / bundle["artifacts"]["r1_r8_review"]["file"])
    assert review["all_passed"] is True
    assert [item["id"] for item in review["requirements"]] == [f"R{i}" for i in range(1, 9)]
    assert all(item["result"] == "PASS" for item in review["requirements"])
    assert review["trust_binding_allowed"] is False
    assert review["promotion_allowed"] is False
    assert review["execution_authority"] == "NONE"


def test_stale_observation_fails_closed(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_stale_test", ASSEMBLER)
    stale = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with pytest.raises(module.DecisionEvidenceError) as exc:
        module.assemble_decision_evidence(
            _observation(stale), output_dir=tmp_path, evaluated_at=_now()
        )
    assert exc.value.code == "SIGNER_ATTESTATION_NOT_VERIFIED"


def test_secret_field_in_observation_is_refused(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_secret_test", ASSEMBLER)
    observation = _observation()
    observation["client_token"] = "must-not-cross"
    with pytest.raises(module.DecisionEvidenceError) as exc:
        module.assemble_decision_evidence(observation, output_dir=tmp_path, evaluated_at=_now())
    assert exc.value.code == "DECISION_EVIDENCE_SECRET_MATERIAL_REFUSED"


def test_bundle_verifier_detects_artifact_tamper(tmp_path: Path) -> None:
    module = _load("hsl_signer_bundle_tamper_test", ASSEMBLER)
    bundle = module.assemble_decision_evidence(
        _observation(), output_dir=tmp_path, evaluated_at=_now()
    )
    capability_path = tmp_path / bundle["artifacts"]["capability_evidence"]["file"]
    capability_path.write_bytes(capability_path.read_bytes() + b" ")
    assert module.verify_decision_evidence_bundle(bundle, tmp_path) is False


def test_output_directory_inside_repository_is_refused() -> None:
    module = _load("hsl_signer_bundle_repo_output_test", ASSEMBLER)
    output_dir = ROOT / ".verification-chg105-output"
    with pytest.raises(module.DecisionEvidenceError) as exc:
        module.assemble_decision_evidence(
            _observation(), output_dir=output_dir, evaluated_at=_now()
        )
    assert exc.value.code == "DECISION_EVIDENCE_REPOSITORY_WRITE_REFUSED"
    assert not output_dir.exists()


def test_cli_assembles_and_verifies_normalized_observation(tmp_path: Path, capsys) -> None:
    module = _load("hsl_signer_bundle_cli_test", ASSEMBLER)
    observation_path = tmp_path / "provider-observation.json"
    observation_path.write_text(json.dumps(_observation()), encoding="utf-8")
    output_dir = tmp_path / "bundle"
    rc = module.main([
        "assemble", "--observation", str(observation_path),
        "--output-dir", str(output_dir), "--evaluated-at", _now(),
    ])
    assert rc == 0
    assembled = json.loads(capsys.readouterr().out)
    assert assembled["state"] == "READY_FOR_HUMAN_DECISION"
    rc = module.main([
        "verify", "--bundle", str(output_dir / "decision-evidence-bundle.json"),
        "--root", str(output_dir),
    ])
    assert rc == 0
    assert "BUNDLE_VERIFY_PASS" in capsys.readouterr().out


def test_assembler_has_no_provider_network_or_credential_use_surface() -> None:
    source = ASSEMBLER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "requests", "httpx", "hvac", "urllib"}
    for banned in ("/v1/auth/", "X-Vault-Token", "vault write", "vault login"):
        assert banned not in source
