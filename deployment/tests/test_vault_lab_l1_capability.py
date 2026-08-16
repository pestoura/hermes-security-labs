from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deployment" / "vault-lab-l1"
COMPOSE = DEPLOY / "compose.yaml"
VAULT_HCL = DEPLOY / "config" / "vault.hcl"
SIGNER_POLICY = DEPLOY / "policies" / "signer.hcl"
OBSERVER_POLICY = DEPLOY / "policies" / "operator-observer.hcl"
BOOTSTRAP = DEPLOY / "bootstrap" / "bootstrap.sh"
VERIFY = DEPLOY / "bootstrap" / "verify-capability.sh"
README = DEPLOY / "README.md"

EXPECTED_IMAGE = (
    "hashicorp/vault:1.21.4@"
    "sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569"
)
EXPECTED_PORT = "127.0.0.1:${VAULT_LAB_L1_HOST_PORT:-18200}:8200"


def _require(path: Path) -> str:
    assert path.is_file(), f"missing CHG-HSL-082 artifact: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _compose() -> tuple[dict, str]:
    text = _require(COMPOSE)
    document = yaml.safe_load(text)
    assert isinstance(document, dict)
    return document, text


def test_vault_runtime_is_immutable_non_dev_and_loopback_only() -> None:
    compose, text = _compose()
    vault = compose["services"]["vault"]

    assert vault["image"] == EXPECTED_IMAGE
    assert vault["command"] == ["server", "-config=/vault/config/vault.hcl"]
    assert vault["ports"] == [EXPECTED_PORT]
    assert "-dev" not in text
    assert "VAULT_DEV_ROOT_TOKEN_ID" not in text
    assert "VAULT_DEV_LISTEN_ADDRESS" not in text
    assert "0.0.0.0:" not in " ".join(vault.get("ports", []))
    assert all(":8201" not in item for item in vault.get("ports", []))


def test_vault_runtime_isolated_and_hardened() -> None:
    compose, _ = _compose()
    vault = compose["services"]["vault"]

    assert vault["networks"] == ["vault-signer-internal"]
    assert compose["networks"]["vault-signer-internal"]["internal"] is True
    assert vault.get("privileged") is not True
    assert vault.get("network_mode") != "host"
    assert vault["security_opt"] == ["no-new-privileges:true"]
    assert vault["cap_drop"] == ["ALL"]
    assert vault["read_only"] is True

    volumes = "\n".join(vault.get("volumes", []))
    assert "/var/run/docker.sock" not in volumes
    assert "/vault/config:ro" in volumes
    assert "/vault/policies:ro" in volumes
    assert "/vault/tls:ro" in volumes
    assert "/vault/data" in volumes

    limits = vault["deploy"]["resources"]["limits"]
    assert limits["cpus"]
    assert limits["memory"]
    assert int(limits["pids"]) > 0


def test_vault_hcl_requires_raft_and_tls() -> None:
    text = _require(VAULT_HCL)

    assert 'storage "raft"' in text
    assert 'path    = "/vault/data"' in text
    assert 'node_id = "hermes-lab-l1-vault-1"' in text
    assert 'listener "tcp"' in text
    assert 'address         = "0.0.0.0:8200"' in text
    assert 'tls_cert_file      = "/vault/tls/server.pem"' in text
    assert 'tls_key_file       = "/vault/tls/server-key.pem"' in text
    assert 'tls_client_ca_file = "/vault/tls/ca.pem"' in text
    assert 'tls_min_version    = "tls12"' in text
    assert re.search(r"(?m)^\s*tls_disable\s*=\s*1\s*$", text) is None
    assert "http://" not in text
    assert 'api_addr     = "https://vault:8200"' in text
    assert 'cluster_addr = "https://vault:8201"' in text


def test_signer_policy_is_exact_path_least_privilege() -> None:
    text = _require(SIGNER_POLICY)

    assert text.count('path "') == 2
    assert 'path "transit/keys/hermes-lab-l1-signer"' in text
    assert 'capabilities = ["read"]' in text
    assert 'path "transit/sign/hermes-lab-l1-signer"' in text
    assert 'capabilities = ["update"]' in text
    assert "*" not in text
    for forbidden in ("create", "delete", "sudo", "patch", "list"):
        assert f'"{forbidden}"' not in text


def test_observer_policy_has_no_management_writes() -> None:
    text = _require(OBSERVER_POLICY)

    assert 'path "sys/health"' in text
    assert 'path "auth/token/lookup-self"' in text
    assert 'path "transit/keys/hermes-lab-l1-signer"' in text
    assert 'capabilities = ["read"]' in text
    for forbidden_path in (
        'path "sys/mounts/*"',
        'path "sys/auth/*"',
        'path "sys/policies/*"',
        'path "transit/keys/*"',
    ):
        assert forbidden_path not in text
    for forbidden_cap in ("create", "update", "delete", "sudo", "patch"):
        assert f'"{forbidden_cap}"' not in text


def test_bootstrap_is_explicit_shamir_3_of_2_and_secret_safe() -> None:
    text = _require(BOOTSTRAP)

    assert "set -euo pipefail" in text
    assert "set -x" not in text
    assert "operator init -key-shares=3 -key-threshold=2" in text
    assert "operator unseal" in text
    assert "read -r -s" in text
    assert "printf '%s\\n' \"$share\" |" in text
    assert "https://" in text
    assert "VAULT_SKIP_VERIFY" in text
    assert "secrets enable -path=transit transit" in text
    assert (
        "write transit/keys/hermes-lab-l1-signer type=ed25519 derived=false "
        "exportable=false allow_plaintext_backup=false"
    ) in text.replace("\\\n", " ")
    assert "auth enable -path=approle approle" in text
    assert "token_no_default_policy=true" in text
    assert "secret_id_num_uses=1" in text
    assert "secret_id_ttl=10m" in text
    assert "-wrap-ttl=5m" in text
    assert "auth/approle/role/hermes-lab-l1-signer/secret-id" in text
    assert "token revoke -self" in text

    forbidden_persistence = (
        "> init.json",
        ">init.json",
        "tee init",
        "tee secret",
        "root-token.txt",
        "secret-id.txt",
        "unseal-keys",
    )
    for marker in forbidden_persistence:
        assert marker not in text.lower()


def test_capability_verifier_emits_public_facts_only() -> None:
    text = _require(VERIFY)

    assert "set -euo pipefail" in text
    assert "transit/keys/hermes-lab-l1-signer" in text
    assert "exportable" in text
    assert "allow_plaintext_backup" in text
    assert "derived" in text
    assert "ed25519" in text.lower()
    assert "VAULT_TOKEN" not in text
    assert "secret_id" not in text.lower()
    assert "root_token" not in text.lower()
    assert "unseal" not in text.lower()


def test_operator_runbook_declares_hitl_and_non_authority() -> None:
    text = _require(README)

    for phrase in (
        "Shamir",
        "3 shares",
        "threshold 2",
        "loopback",
        "response wrapping",
        "root token",
        "NO_DECISION",
        "NO_SELECTION",
        "BLOCKED / HOLD",
        "runtime_status=NOT_RUN",
    ):
        assert phrase in text


def test_signer_governance_remains_unselected_and_campaign_hold() -> None:
    decision = yaml.safe_load(
        (ROOT / "platform" / "assurance" / "signer-human-decision.yaml").read_text(
            encoding="utf-8"
        )
    )
    baseline = yaml.safe_load(
        (ROOT / "platform" / "assurance" / "signer-baseline.yaml").read_text(
            encoding="utf-8"
        )
    )
    campaign = yaml.safe_load(
        (ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert decision["decision"]["state"] == "NO_DECISION"
    assert decision["decision"]["decision_id"] is None
    assert decision["decision"]["selected_class"] is None
    assert baseline["signer_baseline"]["supplier_selection"] == "NO_SELECTION"
    assert baseline["signer_baseline"]["selected_class"] is None
    assert baseline["signer_baseline"]["human_decision_id"] is None
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"


def test_change_record_cannot_claim_live_runtime_or_promotion() -> None:
    path = ROOT / "changes" / "CHG-HSL-082.yaml"
    text = _require(path)
    record = yaml.safe_load(text)

    assert record["id"] == "CHG-HSL-082"
    assert record["issue"] == 426
    assert record["source"]["campaign"] == "VAL-HSL-RUNNER-L1-LIVE-PROMOTION"
    assert record["validation"]["runtime"] == "NOT_RUN"
    assert record["promotion"]["commit"] is None
    assert record["promotion"]["artifactDigest"] is None
