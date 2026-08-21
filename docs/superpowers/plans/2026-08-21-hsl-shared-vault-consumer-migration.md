# HSL Shared Vault Consumer Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-secret, fail-closed HSL consumer contract for the shared Hermes Vault while preserving all signer-selection, trust and live-promotion gates.

**Architecture:** HSL remains a consumer only. A closed YAML descriptor maps the already-existing `VaultSignerAdapter` onto `https://hermes-vault:8200`, `hsl-transit/hsl-signing` and `hsl-signer`; no runtime factory or Vault administration is introduced.

**Tech Stack:** Python 3, pytest, YAML, JSON Schema Draft 7, existing HSL Vault signer adapter.

**Spec:** `docs/superpowers/specs/2026-08-21-hsl-shared-vault-consumer-migration-design.md`

## Global Constraints

- Never store SecretID, Vault token, Shamir share, private key, passphrase or recovery locator.
- No shared-Vault administration from HSL consumer artefacts.
- No automatic fallback to legacy signing.
- Do not modify signer decision/baseline/trust state.
- Repository acceptance is not live provider acceptance.

---
### Task 1: Closed shared-Vault consumer descriptor

**Files:**
- Create: `deployment/shared-vault-hsl/consumer-contract.schema.json`
- Create: `deployment/shared-vault-hsl/consumer-contract.yaml`
- Test: `deployment/tests/test_shared_vault_hsl_consumer.py`

**Interfaces:**
- Consumes: ADR-0018 canonical endpoint/mount/key/AppRole values.
- Produces: validated non-secret descriptor used by later adapter-compatibility tests.

- [ ] **Step 1: Write failing schema/descriptor tests**

```python
def test_shared_vault_descriptor_exact_contract():
    doc = yaml.safe_load(DESCRIPTOR.read_text())
    assert doc["vault_addr"] == "https://hermes-vault:8200"
    assert doc["transit_mount"] == "hsl-transit"
    assert doc["key_name"] == "hsl-signing"
    assert doc["approle_mount"] == "approle"
    assert doc["approle_name"] == "hsl-signer"
```

- [ ] **Step 2: Run RED**

Run: `python3 -m pytest -q deployment/tests/test_shared_vault_hsl_consumer.py -p no:cacheprovider`
Expected: FAIL because descriptor/schema do not exist.
- [ ] **Step 3: Implement minimal closed schema and descriptor**

Descriptor fields are exactly:

```yaml
schema_version: hsl.shared-vault-consumer/v1
provider: hermes-shared-vault
vault_addr: https://hermes-vault:8200
transit_mount: hsl-transit
key_name: hsl-signing
approle_mount: approle
approle_name: hsl-signer
role_id_ref: secretref://hermes-vault/hsl-signer/role-id
secret_id_ref: secretref://hermes-vault/hsl-signer/secret-id
activation: NOT_RUN
```

The JSON schema sets `additionalProperties: false` and const-enforces provider, mount, key, AppRole and `activation: NOT_RUN`.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m pytest -q deployment/tests/test_shared_vault_hsl_consumer.py -p no:cacheprovider`
Expected: descriptor/schema tests PASS.

- [ ] **Step 5: Commit**

```bash
git add deployment/shared-vault-hsl deployment/tests/test_shared_vault_hsl_consumer.py
git commit -m "feat(vault): add shared HSL consumer contract"
```

---
### Task 2: Prove compatibility with the existing adapter

**Files:**
- Modify: `deployment/tests/test_shared_vault_hsl_consumer.py`
- Read-only dependency: `platform/assurance/vault_signer_adapter.py`

**Interfaces:**
- Consumes: Task 1 descriptor.
- Produces: proof that no adapter rewrite is required.

- [ ] **Step 1: Add failing compatibility test**

```python
def test_descriptor_builds_existing_vault_signer_config():
    doc = yaml.safe_load(DESCRIPTOR.read_text())
    cfg = vault.VaultSignerConfig(
        vault_addr=doc["vault_addr"], transit_mount=doc["transit_mount"],
        key_name=doc["key_name"], approle_mount=doc["approle_mount"],
        role_id_ref=doc["role_id_ref"], secret_id_ref=doc["secret_id_ref"],
    )
    assert cfg.transit_mount == "hsl-transit"
```

- [ ] **Step 2: Run RED/GREEN and confirm `vault_signer_adapter.py` is unchanged**

Run the targeted test, then `git diff -- platform/assurance/vault_signer_adapter.py` and require an empty diff.

- [ ] **Step 3: Add secret/admin negative guards**

Assert the descriptor contains no `hvs.`, `SecretID`, token values, `vault secrets enable`, `vault auth enable`, `vault policy write` or `vault write auth/approle` command text.

- [ ] **Step 4: Commit**

```bash
git add deployment/tests/test_shared_vault_hsl_consumer.py
git commit -m "test(vault): prove shared consumer adapter compatibility"
```

---
### Task 3: Mark the isolated Vault package as legacy/non-authoritative

**Files:**
- Modify: `deployment/vault-lab-l1/README.md`
- Create: `deployment/shared-vault-hsl/README.md`
- Test: `deployment/tests/test_shared_vault_hsl_consumer.py`

- [ ] **Step 1: Add RED tests** requiring the shared README to state provider ownership and HITL credential delivery, and the legacy README to state `NO_NEW_SIGNING_AUTHORITY` and `NO_AUTOMATIC_FALLBACK`.

- [ ] **Step 2: Implement minimal documentation** without deleting the legacy package or changing compose/runtime files.

- [ ] **Step 3: Run GREEN**

Run: `python3 -m pytest -q deployment/tests/test_shared_vault_hsl_consumer.py -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add deployment/shared-vault-hsl/README.md deployment/vault-lab-l1/README.md deployment/tests/test_shared_vault_hsl_consumer.py
git commit -m "docs(vault): define shared consumer and legacy boundary"
```

---

### Task 4: Record CHG-HSL-085 honestly

**Files:**
- Create: `changes/CHG-HSL-085.yaml`
- Test: existing change-record/schema gates plus `deployment/tests/test_shared_vault_hsl_consumer.py`

The record must state `runtime: NOT_RUN`, risk `LOW`, classification `IMPROVEMENT`, campaign `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`, and explicitly preserve `NO_DECISION`, `NO_SELECTION`, trust absent and HOLD.

- [ ] Run JDS/source-of-truth validation and commit the record.

---
### Task 5: Regression, exact-SHA and PR

**Files:** all CHG-HSL-085 files.

- [ ] Run targeted deployment tests.
- [ ] Run the canonical repository validation/source-of-truth gates used by `main`.
- [ ] Run security checks and `git diff --check`.
- [ ] Verify no changes to `platform/assurance/signer-human-decision.yaml`, `platform/assurance/signer-baseline.yaml` or `platform/assurance/vault_signer_adapter.py`.
- [ ] Push branch, open PR, require all GitHub checks GREEN, merge with exact-head SHA and verify post-merge CI on the resulting main SHA.

## Post-merge live gate

After CHG-HSL-085 repository acceptance, do **not** mark live capability PASS. The next gate is operator-only shared Vault bootstrap and sanitized provider evidence. RoleID/SecretID/token handling remains HITL and is never copied into Git, ChatGPT, Context Core or logs.

## Self-review

- Spec coverage: descriptor, ownership, adapter reuse, legacy continuity, no activation and live handoff are all mapped to Tasks 1–5.
- Placeholder scan: no TBD/TODO/XXX or unspecified implementation step remains.
- Type consistency: descriptor values map directly to the existing `VaultSignerConfig` constructor; no new application type is introduced.
