"""Repository-only tests for TB1 signer/trust-store deployment prerequisites.

No provider, secret, trust-store installation or runtime service is touched.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "deployment" / "runtime-promotion" / "tb1_authorization_preflight.py"
EXAMPLE = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "tb1-authorization-deployment-descriptor.example.yaml"
)
DESCRIPTOR_SCHEMA = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "tb1-authorization-deployment-descriptor.schema.json"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load("tb1_authorization_deployment_preflight_test", PREFLIGHT_PATH)


def _descriptor() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))


def _findings(descriptor: dict[str, Any]) -> tuple[str, ...]:
    return preflight.run_preflight(descriptor).findings


def test_example_descriptor_passes_without_claiming_runtime() -> None:
    result = preflight.run_preflight(_descriptor())
    assert result.ok is True
    assert result.findings == ()
    assert result.runtime_status == "NOT_RUN"
    assert result.authority == "hermes-control-plane"
    assert result.provider_kind == "HSM"
    assert result.key_id == "tb1-authorization-example-ed25519"
    assert result.trust_key_count == 1


def test_cli_json_is_sanitized_and_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(PREFLIGHT_PATH), "--json", "check"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["runtime_status"] == "NOT_RUN"
    assert report["provider_kind"] == "HSM"
    assert "public_key" not in report
    assert "document" not in report


def test_descriptor_schema_is_strict_and_runtime_cannot_claim_promotion() -> None:
    descriptor = _descriptor()
    descriptor["runtime_status"] = "RUNNING"
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.run_preflight(descriptor)
    assert exc.value.code == "DESCRIPTOR_INVALID"

    descriptor = _descriptor()
    descriptor["enable_now"] = True
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.run_preflight(descriptor)
    assert exc.value.code == "DESCRIPTOR_INVALID"


def test_local_private_key_flag_cannot_be_enabled() -> None:
    descriptor = _descriptor()
    descriptor["signer"]["private_key_local"] = True
    with pytest.raises(preflight.PreflightError):
        preflight.run_preflight(descriptor)


def test_secret_material_fields_fail_closed() -> None:
    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["keys"][0]["private_key"] = "forbidden"
    result = preflight.run_preflight(descriptor)
    assert result.ok is False
    assert any("secret/private material field is forbidden" in f for f in result.findings)
    assert any("trust store schema invalid" in f for f in result.findings)


def test_provider_reference_is_non_secret_logical_reference() -> None:
    for value in (
        "https://user:password@example.invalid/key",
        "vault:key?token=secret",
        "key#fragment",
        "key ref with spaces",
    ):
        descriptor = _descriptor()
        descriptor["signer"]["provider_ref"] = value
        with pytest.raises(preflight.PreflightError):
            preflight.run_preflight(descriptor)


def test_signer_key_must_exist_exactly_once_and_be_active() -> None:
    descriptor = _descriptor()
    descriptor["signer"]["key_id"] = "missing-key"
    assert any("match exactly one" in f for f in _findings(descriptor))

    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["keys"][0]["state"] = "revoked"
    assert any("must be active" in f for f in _findings(descriptor))


def test_duplicate_trust_key_ids_fail_closed() -> None:
    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["keys"].append(
        copy.deepcopy(descriptor["trust_store"]["document"]["keys"][0])
    )
    findings = _findings(descriptor)
    assert any("duplicate trust-store key_id" in f for f in findings)
    assert any("match exactly one" in f for f in findings)


def test_signer_algorithm_must_match_trust_key() -> None:
    descriptor = _descriptor()
    descriptor["signer"]["algorithm"] = "ECDSA-P256-SHA256"
    findings = _findings(descriptor)
    assert any("signer algorithm must match" in f for f in findings)


def test_public_key_must_be_valid_and_match_declared_algorithm() -> None:
    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["keys"][0]["public_key"] = "bm90LWRlcg=="
    assert any("public key does not match algorithm" in f for f in _findings(descriptor))

    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["keys"][0]["algorithm"] = "ECDSA-P256-SHA256"
    findings = _findings(descriptor)
    assert any("public key does not match algorithm" in f for f in findings)
    assert any("signer algorithm must match" in f for f in findings)


def test_domain_and_purpose_are_purpose_bound() -> None:
    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["domain"] = "hex0r.roe.signing.v1"
    findings = _findings(descriptor)
    assert any("trust store schema invalid" in f for f in findings)
    assert any("trust-store domain" in f for f in findings)

    descriptor = _descriptor()
    descriptor["trust_store"]["document"]["purpose"] = "roe-signing"
    findings = _findings(descriptor)
    assert any("trust store schema invalid" in f for f in findings)
    assert any("trust-store purpose" in f for f in findings)


def test_trust_store_install_path_is_restricted_to_runtime_or_config_roots() -> None:
    for path in ("relative.json", "/tmp/trust.json", "/home/user/trust.json"):
        descriptor = _descriptor()
        descriptor["trust_store"]["install_path"] = path
        with pytest.raises(preflight.PreflightError):
            preflight.run_preflight(descriptor)


def test_validity_window_order_is_checked() -> None:
    descriptor = _descriptor()
    key = descriptor["trust_store"]["document"]["keys"][0]
    key["not_before"] = "2026-08-10T12:00:00Z"
    key["not_after"] = "2026-08-10T11:00:00Z"
    assert any("validity window is invalid" in f for f in _findings(descriptor))


def test_descriptor_schema_itself_is_strict() -> None:
    schema = json.loads(DESCRIPTOR_SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["signer"]["additionalProperties"] is False
    assert schema["properties"]["signer"]["properties"]["private_key_local"] == {
        "const": False
    }
    assert schema["properties"]["runtime_status"] == {"const": "NOT_RUN"}


def test_preflight_has_no_provisioning_or_private_key_loader() -> None:
    source = PREFLIGHT_PATH.read_text(encoding="utf-8")
    assert "load_pem_private_key" not in source
    assert "load_der_private_key" not in source
    assert "private_bytes(" not in source
    assert "subprocess" not in source
    assert "socket" not in source
    assert "os.system" not in source

    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "pwd", "grp", "ctypes", "os"}


def test_missing_descriptor_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.load_descriptor(tmp_path / "missing.yaml")
    assert exc.value.code == "DESCRIPTOR_UNREADABLE"
