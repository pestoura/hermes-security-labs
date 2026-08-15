# Signer ↔ trust-generation evidence bridge design

Date: 2026-08-15
Change: CHG-HSL-074
Status: approved continuation design

## Problem

The repository already has three independent fail-closed contracts:

1. external signer attestation verification (`runtime_signer_attestation.py`);
2. public trust-store generation/freshness/rotation/revocation (`trust_store_lifecycle.py`);
3. explicit runtime trust installation (`trust_binding.py`).

The missing piece is a repository-only evidence composition proving that the *same* externally attested signer key is present as the active key in an accepted-for-review trust-store generation. This must not install trust, select a provider, or grant runtime/promotion authority.

## Design

Add `platform/assurance/signer_trust_manifest.py` producing a content-addressed public manifest only when all supplied canonical outputs agree.

Inputs:
- canonical signer verifier result as a safe mapping;
- the original normalized signer attestation carrying source evidence ref/digest;
- one canonical trust-store generation;
- its canonical lifecycle assessment.

Acceptance requires:
- signer verifier result has `signer_attestation_checks_passed=true` and `source_evidence_verified=true`;
- provider class is one of `VAULT`, `KMS`, `HSM` (never standalone `PKCS11`);
- original attestation is `OBSERVED`, active, signing enabled, non-exportable and exactly matches the verifier result identity;
- generation passes the existing lifecycle validator;
- assessment is `ACCEPT_FOR_REVIEW`, has no codes, refers to the exact generation, and has no activation/authorization/execution effect;
- the exact signer `key_id` occurs once in the generation, is `active`, and has matching algorithm + `public_key_sha256 == public_key_spki_sha256`.

Output fields are public/auditable only: manifest id, provider kind/ref, key identity/algorithm/SPKI hash, signer source evidence ref/digest, generation id/sequence/trust-store digest and explicit no-authority flags.

The manifest always carries:
- `trust_binding_allowed=false`;
- `automatic_activation=false`;
- `activation_effect=NONE`;
- `authorization_effect=NONE`;
- `execution_authority=NONE`;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`.

## Non-goals

- no Vault/KMS/HSM/PKCS11 calls;
- no key generation or signing;
- no trust-store file writes or installation;
- no provider/candidate selection;
- no EvidenceVerifier replacement;
- no promotion or Runner effect.

## Follow-up

The output may later be custodized as the `trust_store_manifest` evidence class required by the human signer-decision contract, but CHG-HSL-074 itself does not create an approved human decision or satisfy provider evidence that has not been observed live.
