from pathlib import Path
import importlib.util
import json

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
