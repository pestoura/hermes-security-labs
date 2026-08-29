# HSL Signer Decision Evidence Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, secret-free assembly path for the four evidence classes required by issue #403 before `APPROVED + NO_SELECTION`.

**Architecture:** Normalize one public Vault Transit observation, build content-addressed capability/attestation/trust/R1–R8 artifacts, and bind them into a no-authority readiness manifest. Reuse canonical signer-attestation and trust lifecycle verifiers; never persist or handle Secret Zero credentials.

**Tech Stack:** Python 3.12+, PyYAML, jsonschema, cryptography, existing HSL assurance/runtime modules.

**Spec:** `docs/superpowers/specs/2026-08-29-hsl-signer-decision-evidence-bundle-design.md`

## Global Constraints

- Secret Zero issuance/wrapping/unwrap/AppRole credential use remains operator-only HITL.
- No RoleID, SecretID, wrapping token, Vault token, private key or passphrase may enter repository evidence.
- `supplier_selection=NO_SELECTION`, trust unbound, `promotion_allowed=false`, `execution_authority=NONE`, `runtime_status=NOT_RUN` throughout CHG-HSL-105.
- Use existing canonical signer attestation and trust lifecycle code; do not create parallel security semantics.

---
### Task 1: Vault provider observation contract

**Files:**
- Create: `deployment/shared-vault-hsl/signer-evidence/provider-observation.schema.json`
- Create: `deployment/shared-vault-hsl/signer-evidence/vault_provider_observation.py`
- Test: `deployment/tests/test_vault_signer_provider_observation.py`

**Interfaces:**
- Consumes: sanitized Vault key metadata plus explicit capability/audit booleans.
- Produces: `normalize_provider_observation(raw_key_response, observed_at, capability_checks, bootstrap_evidence, audit_evidence) -> dict[str, Any]`.

- [ ] Write tests proving valid Ed25519 metadata normalizes to public SPKI identity and all secret-like fields fail closed.
- [ ] Run the targeted tests and observe RED because the module/schema do not exist.
- [ ] Implement the closed schema and normalizer; derive provider/key identity and SPKI SHA-256, reject non-admissible key state and any secret/private material.
- [ ] Run targeted tests to GREEN and validate the example schema with jsonschema.

### Task 2: Four-artifact evidence assembler

**Files:**
- Create: `deployment/shared-vault-hsl/signer-evidence/signer_decision_evidence.py`
- Create: `deployment/shared-vault-hsl/signer-evidence/decision-evidence-bundle.schema.json`
- Test: `deployment/tests/test_signer_decision_evidence_bundle.py`

**Interfaces:**
- Consumes: one normalized provider observation from Task 1.
- Produces: capability evidence, TB1 signer attestation, public trust-store manifest, R1–R8 review, and one `READY_FOR_HUMAN_DECISION|HOLD` bundle.
- [ ] Write tests for deterministic content digests, canonical refs, attestation verification, trust generation/manifests and eight passing R1–R8 entries.
- [ ] Run the targeted bundle tests and observe RED before implementation.
- [ ] Implement the assembler using `runtime_signer_attestation.verify_signer_attestation`, `trust_store_lifecycle.build_generation/assess_transition`, and `signer_trust_manifest.build_signer_trust_manifest`.
- [ ] Make `READY_FOR_HUMAN_DECISION` require all four evidence refs/digests and hard-code no-authority fields.
- [ ] Run targeted tests to GREEN, including negative cases for missing audit evidence, stale observation, SPKI mismatch and secret-field injection.

### Task 3: Operator handoff and governance

**Files:**
- Create: `deployment/shared-vault-hsl/signer-evidence/README.md`
- Create: `deployment/shared-vault-hsl/signer-evidence/templates/provider-observation.example.yaml`
- Create: `changes/CHG-HSL-105.yaml`
- Modify: `deployment/shared-vault-hsl/README.md`

**Interfaces:**
- Documents the one-window operator boundary without embedding any credentials or custody locators.
- Leaves #403 at `NO_DECISION + NO_SELECTION` until a later live bundle actually reaches READY.

- [ ] Document the hardened consumer requirement and fresh consumer `/32` rule from CHG-HSL-104.
- [ ] Document the operator-only credential steps as a boundary, not as automated code; repository tooling begins only after authenticated public metadata is available.
- [ ] Add a NOT_RUN example that is schema-valid but mechanically unable to become READY.
- [ ] Record CHG-HSL-105 with issue #403, `runtime: NOT_RUN`, no trust/promotion authority and exact validation evidence.
- [ ] Run YAML/schema, deployment, platform signer/trust, docs and JDS regression gates; review `git diff --check` and secret-pattern scans before commit/PR.
