# Vault LAB_L1 Operational Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-safe, fail-closed deployment package for an isolated real Vault LAB_L1 capability supporting the merged `VaultSignerAdapter`, while preserving `NO_DECISION`, `NO_SELECTION`, unbound trust and `BLOCKED/HOLD`.

**Architecture:** A single-node Vault 1.21.4 server uses Integrated Storage/Raft and mandatory TLS, publishes API only to host loopback, and joins a dedicated Docker `internal: true` signer network. Bootstrap uses Shamir 3/2, an ephemeral initial root token, Transit Ed25519 signing and least-privilege AppRole with response-wrapped single-use SecretID. Static CI proves the package is safe before any live Hermes execution.

**Tech Stack:** Docker Compose, HashiCorp Vault 1.21.4, HCL, POSIX/Bash shell, Python/pytest, PyYAML.

## Global Constraints

- Image: `hashicorp/vault:1.21.4@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569`.
- No Vault dev mode or plaintext HTTP fallback.
- Single node, Integrated Storage/Raft, TLS mandatory, manual Shamir 3 shares / threshold 2.
- Host publication is loopback-only; port 8201 is never host-published.
- Dedicated signer network is Docker `internal: true`; target/Kali/Runner environments do not join it.
- Signer AppRole has only exact key metadata read and exact key sign update permissions.
- Transit key is Ed25519, non-derived, `exportable=false`, `allow_plaintext_backup=false`.
- SecretID is response-wrapped, single-use and short-lived.
- Initial root token is bootstrap-only and revoked before operational acceptance.
- No Shamir share, root token, SecretID or Vault client token may be written to Git/log/evidence.
- Governance remains `NO_DECISION + NO_SELECTION + BLOCKED/HOLD`; no trust binding or live Runner effect.

---

### Task 1: RED static deployment contract

**Files:**
- Create: `deployment/tests/test_vault_lab_l1_capability.py`
- Create: `changes/CHG-HSL-082.yaml`

**Interfaces:**
- Consumes: repository paths under `deployment/vault-lab-l1/` which do not exist yet.
- Produces: executable acceptance contract for compose, HCL policies/config, bootstrap scripts and governance invariants.

- [ ] **Step 1: Write failing tests**

Tests load repository files directly and assert:

```python
assert compose["services"]["vault"]["image"] == EXPECTED_IMAGE
assert compose["services"]["vault"]["ports"] == ["127.0.0.1:${VAULT_LAB_L1_HOST_PORT:-18200}:8200"]
assert compose["networks"]["vault-signer-internal"]["internal"] is True
assert "8201" not in repr(compose["services"]["vault"].get("ports", []))
assert "-dev" not in compose_text
assert 'storage "raft"' in vault_hcl
assert "tls_disable" not in vault_hcl or "tls_disable = 0" in vault_hcl
assert 'path "transit/keys/hermes-lab-l1-signer"' in signer_policy
assert 'capabilities = ["read"]' in signer_policy
assert 'path "transit/sign/hermes-lab-l1-signer"' in signer_policy
assert 'capabilities = ["update"]' in signer_policy
assert "key-shares=3" in bootstrap
assert "key-threshold=2" in bootstrap
assert "-wrap-ttl=" in bootstrap
assert "secret_id_num_uses=1" in bootstrap
```

The test must also load canonical governance YAML and prove no promotion/selection/trust state changes.

- [ ] **Step 2: Commit tests-first checkpoint**

```bash
git add deployment/tests/test_vault_lab_l1_capability.py changes/CHG-HSL-082.yaml
git commit -m "test: define CHG-HSL-082 Vault deployment contract"
```

- [ ] **Step 3: Open draft PR and verify RED in CI**

Expected: deployment/static validation fails because `deployment/vault-lab-l1/*` is missing. Existing unrelated suites should remain green where independently runnable.

### Task 2: GREEN hardened Vault runtime package

**Files:**
- Create: `deployment/vault-lab-l1/compose.yaml`
- Create: `deployment/vault-lab-l1/config/vault.hcl`
- Create: `deployment/vault-lab-l1/policies/signer.hcl`
- Create: `deployment/vault-lab-l1/policies/operator-observer.hcl`

**Interfaces:**
- Consumes: operator-managed TLS files mounted read-only under `/vault/tls`.
- Produces: deterministic Vault service with Raft/TLS and least-privilege policies.

- [ ] **Step 1: Implement compose minimally to satisfy contract**

Required service shape:

```yaml
services:
  vault:
    image: hashicorp/vault:1.21.4@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569
    command: ["server", "-config=/vault/config/vault.hcl"]
    ports:
      - "127.0.0.1:${VAULT_LAB_L1_HOST_PORT:-18200}:8200"
    networks:
      - vault-signer-internal
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    read_only: true
```

Add only the minimum capability required for Vault memory locking if the pinned runtime requires it; otherwise disable mlock explicitly in HCL and keep all capabilities dropped. Mount config/policies/TLS read-only and Raft data writable. No Docker socket, privileged mode, host network or port 8201 publication.

- [ ] **Step 2: Implement `vault.hcl`**

Use:

```hcl
ui = false
disable_mlock = true

storage "raft" {
  path    = "/vault/data"
  node_id = "hermes-lab-l1-vault-1"
}

listener "tcp" {
  address            = "0.0.0.0:8200"
  cluster_address    = "0.0.0.0:8201"
  tls_cert_file      = "/vault/tls/server.pem"
  tls_key_file       = "/vault/tls/server-key.pem"
  tls_client_ca_file = "/vault/tls/ca.pem"
  tls_min_version    = "tls12"
}

api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"
```

- [ ] **Step 3: Implement exact signer policy**

```hcl
path "transit/keys/hermes-lab-l1-signer" {
  capabilities = ["read"]
}

path "transit/sign/hermes-lab-l1-signer" {
  capabilities = ["update"]
}
```

No wildcard allow stanza.

- [ ] **Step 4: Implement observation-only operator policy**

Allow health/self/token lookup and exact public Transit key metadata needed for attestation, without policy/auth/mount/key lifecycle writes.

- [ ] **Step 5: Run targeted tests and commit GREEN runtime package**

```bash
pytest -q deployment/tests/test_vault_lab_l1_capability.py
```

Expected: runtime/config/policy tests pass; bootstrap-script tests may remain RED until Task 3.

### Task 3: GREEN secret-safe bootstrap and verification scripts

**Files:**
- Create: `deployment/vault-lab-l1/bootstrap/bootstrap.sh`
- Create: `deployment/vault-lab-l1/bootstrap/verify-capability.sh`

**Interfaces:**
- Consumes: `VAULT_ADDR`, `VAULT_CACERT` and secret values only via stdin/environment supplied by an operator secret boundary.
- Produces: Vault configuration and sanitized capability JSON/text with no credentials.

- [ ] **Step 1: Implement preflight helpers**

The script must use `set -euo pipefail`, require HTTPS `VAULT_ADDR`, require readable CA certificate, reject `VAULT_SKIP_VERIFY`, and provide a `vault_safe` wrapper with no shell tracing.

- [ ] **Step 2: Implement explicit initialization mode**

Initialization is never implicit. A dedicated subcommand calls:

```bash
vault operator init -key-shares=3 -key-threshold=2
```

It writes only to the operator terminal/stdout and the script must not redirect the response to a repository file. README warns the operator to capture/distribute shares out-of-band.

- [ ] **Step 3: Implement unseal mode without argv secrets**

Read each share silently from stdin/TTY and pass it to `vault operator unseal` through stdin. Never place a share in command-line arguments or logs.

- [ ] **Step 4: Implement bootstrap configuration under initial root token**

Commands must:

```bash
vault secrets enable -path=transit transit
vault write transit/keys/hermes-lab-l1-signer type=ed25519 derived=false exportable=false allow_plaintext_backup=false
vault auth enable -path=approle approle
vault policy write hermes-lab-l1-signer /vault/policies/signer.hcl
vault policy write hermes-lab-l1-observer /vault/policies/operator-observer.hcl
vault write auth/approle/role/hermes-lab-l1-signer \
  token_policies=hermes-lab-l1-signer \
  token_no_default_policy=true \
  token_ttl=10m \
  token_max_ttl=30m \
  secret_id_num_uses=1 \
  secret_id_ttl=10m
vault write -wrap-ttl=5m -f auth/approle/role/hermes-lab-l1-signer/secret-id
```

The wrapped response is delivered only to the operator output channel and is not parsed into repository evidence.

- [ ] **Step 5: Implement capability verification**

Use only sanitized/public fields to emit a capability report. Prove exact key properties and run negative capability checks for management paths with the signer identity.

- [ ] **Step 6: Implement root revocation command**

Provide an explicit final bootstrap subcommand invoking self-revocation of the current bootstrap root token only after limited operator/signer verification succeeds. Do not persist the token.

- [ ] **Step 7: Run targeted tests and commit**

```bash
pytest -q deployment/tests/test_vault_lab_l1_capability.py
```

Expected: PASS.

### Task 4: Documentation and governance hardening

**Files:**
- Create: `deployment/vault-lab-l1/README.md`
- Modify: `changes/CHG-HSL-082.yaml`
- Modify: `docs/roadmap/provider-neutral-signer-boundary-2026-08-15.md`

**Interfaces:**
- Consumes: completed repository package.
- Produces: operator runbook and explicit GREEN-REPO / runtime-NOT_RUN state.

- [ ] **Step 1: Document operator sequence and HITL boundary**

Document TLS prerequisites, compose startup, init/unseal, bootstrap, SecretID handoff, verification, root revocation, evidence capture, shutdown/reset and emergency HOLD.

- [ ] **Step 2: Explicitly document non-authority**

State that repository GREEN does not prove live provider custody, does not approve #403, does not bind trust and does not authorize target effects.

- [ ] **Step 3: Set change state to repository acceptance only after CI**

Before CI keep `state: IN_PROGRESS`; after exact-head GREEN update validation fields to PASS while keeping `runtime: NOT_RUN`.

### Task 5: Full CI, security and exact-SHA closure

**Files:**
- No new production files unless failures identify a required fix.

**Interfaces:**
- Consumes: final PR head.
- Produces: exact-SHA evidence and merge candidate.

- [ ] **Step 1: Run/observe full repository CI**

Require validate, security, release governance, private VAmPI and Exact-SHA gates where configured.

- [ ] **Step 2: Fix only causal failures**

Use systematic debugging for any unexpected failure. Do not weaken security scanners or tests.

- [ ] **Step 3: Update PR/change record with exact head evidence**

Record exact SHA and run IDs; `runtime: NOT_RUN` remains unchanged.

- [ ] **Step 4: Merge only exact verified head**

Use squash merge with expected head SHA.

- [ ] **Step 5: Verify post-merge exact SHA**

All canonical gates must pass on `main` before closing #426 repository phase.

### Task 6: Live Hermes execution gate

**Files:**
- Evidence generated outside Git or as sanitized evidence artifacts only through approved repository contracts.

**Interfaces:**
- Consumes: merged deployment package plus Hermes runtime access and operator-controlled TLS/secret material.
- Produces: real provider/capability evidence for #403.

- [ ] **Step 1: Stop if Hermes runtime control plane is unavailable**

This is a real external technical blocker, not a repository blocker.

- [ ] **Step 2: Execute TLS provisioning, compose startup and initialization**

Do not expose secret values to chat/Git/logs.

- [ ] **Step 3: Operator/HITL handles Shamir/root/SecretID secret-bearing moments**

Proceed automatically around those moments; request human interaction only where the secret boundary makes it unavoidable.

- [ ] **Step 4: Capture sanitized live capability evidence**

Do not change `NO_DECISION`, `NO_SELECTION`, trust or promotion state.

- [ ] **Step 5: Feed evidence to #403**

Only after capability evidence, signer attestation, trust public identity manifest and R1-R8 review are complete may the separate human decision lifecycle advance.
