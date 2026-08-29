# Shared-Vault signer decision evidence

This directory implements CHG-HSL-105, the repository-side preparation for issue #403.

It does **not** perform Secret Zero, issue credentials, authenticate to Vault, select a runtime candidate, install trust or promote Runner execution. Credential issuance, wrapping, unwrap and AppRole login remain operator-only HITL boundaries.

## Purpose

After an authorized operator session has produced sanitized public Vault Transit metadata, the tooling here can:

1. normalize and validate the public provider observation;
2. bind it to content-addressed capability evidence;
3. build and verify the canonical TB1 signer attestation;
4. build a public trust-store snapshot and reviewed lifecycle generation;
5. compose the canonical signer/trust manifest;
6. produce a deterministic R1–R8 review;
7. emit a four-reference bundle for the later human `APPROVED + NO_SELECTION` decision.

`READY_FOR_HUMAN_DECISION` means only that the evidence package is complete. It grants no trust, authorization, execution or promotion authority.
## Required live inputs

The repository assembler accepts only an `OBSERVED` provider document that has already been sanitized. The observation must prove:

- the exact shared Vault Transit key is active Ed25519;
- server-side signing is enabled;
- the private key is non-exportable;
- plaintext backup is disabled;
- bounded key-read and sign/verify checks passed;
- required `sys/*` and `auth/*` negative checks passed;
- provider audit attribution passed;
- no secret material was persisted;
- bootstrap and audit evidence are bound by canonical `evidence://` references and SHA-256.

The normalizer rejects secret/private fields recursively. The assembler stages output outside the Git repository and refuses repository paths. Sanitized evidence may be reviewed and copied into Git only through a later governed change.

## Consumer network rule

Use the hardened CHG-HSL-104 consumer. Observe that consumer's IPv4 address immediately before any operator-only credential issuance and bind the credential/token to that fresh `/32`. Do not reuse the historical CHG-HSL-103 address and do not assume the probe and consumer share an address.

## Current authority state

CHG-HSL-105 preserves `NO_DECISION + NO_SELECTION`, trust absent/unbound, `promotion_allowed=false`, `execution_authority=NONE` and `runtime_status=NOT_RUN`.

## Repository entry points

`vault_provider_observation.py normalize` reads public Vault key metadata from standard input. It requires explicit pass flags for key read, bounded sign/verify, negative `sys`/`auth`, audit attribution and residue checks, plus sanitized bootstrap/audit evidence refs and digests. Missing checks fail closed.

`signer_decision_evidence.py assemble --observation <sanitized-file> --output-dir <external-dir>` creates the content-addressed evidence set. The output directory must be outside the repository.

`signer_decision_evidence.py verify --bundle <bundle-file> --root <external-dir>` rechecks file digests, canonical refs, cross-artifact identity and no-authority invariants without re-running a live freshness check.
