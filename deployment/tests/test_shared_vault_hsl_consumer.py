from pathlib import Path
import importlib.util
import json
import sys

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONSUMER_DIR = ROOT / "deployment" / "shared-vault-hsl"
SCHEMA = CONSUMER_DIR / "consumer-contract.schema.json"
DESCRIPTOR = CONSUMER_DIR / "consumer-contract.yaml"
VAULT_ADAPTER = ROOT / "platform" / "assurance" / "vault_signer_adapter.py"
LEGACY_README = ROOT / "deployment" / "vault-lab-l1" / "README.md"
SHARED_README = CONSUMER_DIR / "README.md"


def _doc():
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_shared_vault_descriptor_validates_against_closed_schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    doc = _doc()
    jsonschema.Draft7Validator(schema).validate(doc)
    assert schema.get("additionalProperties") is False


def test_shared_vault_descriptor_exact_contract():
    doc = _doc()
    assert doc["schema_version"] == "hsl.shared-vault-consumer/v1"
    assert doc["provider"] == "hermes-shared-vault"
    assert doc["vault_addr"] == "https://hermes-vault:8200"
    assert doc["transit_mount"] == "hsl-transit"
    assert doc["key_name"] == "hsl-signing"
    assert doc["approle_mount"] == "approle"
    assert doc["approle_name"] == "hsl-signer"
    assert doc["role_id_ref"] == "secretref://hermes-vault/hsl-signer/role-id"
    assert doc["secret_id_ref"] == "secretref://hermes-vault/hsl-signer/secret-id"
    assert doc["activation"] == "NOT_RUN"


def _load_adapter_module():
    spec = importlib.util.spec_from_file_location(
        "chg_hsl_085_vault_adapter", VAULT_ADAPTER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_descriptor_builds_existing_vault_signer_config():
    doc = _doc()
    vault = _load_adapter_module()
    cfg = vault.VaultSignerConfig(
        vault_addr=doc["vault_addr"],
        transit_mount=doc["transit_mount"],
        key_name=doc["key_name"],
        approle_mount=doc["approle_mount"],
        role_id_ref=doc["role_id_ref"],
        secret_id_ref=doc["secret_id_ref"],
    )
    assert cfg.vault_addr == "https://hermes-vault:8200"
    assert cfg.transit_mount == "hsl-transit"
    assert cfg.key_name == "hsl-signing"
    assert cfg.approle_mount == "approle"


def test_descriptor_is_reference_only_and_contains_no_admin_commands():
    text = DESCRIPTOR.read_text(encoding="utf-8")
    assert "secretref://" in text
    for forbidden in (
        "hvs.",
        "vault secrets enable",
        "vault auth enable",
        "vault policy write",
        "vault write auth/approle",
        "VAULT_TOKEN=",
        "SecretID:",
    ):
        assert forbidden not in text
