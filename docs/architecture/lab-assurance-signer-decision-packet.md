# Lab assurance signer — next-decision packet (human supplier choice)

**Status:** Decision packet — **current `supplier_selection: NO_SELECTION`**. This document records
the *deterministic* next step for the future human signer choice. It selects nothing. It is the
companion to [lab-assurance-signer-requirements.md](lab-assurance-signer-requirements.md) (the
accepted R1–R8 baseline) and to the evaluation-only candidate model in
`platform/assurance/signer_selection.py`.

> The technology/product choice remains a separate, explicit human-in-the-loop decision. No code
> path here auto-selects a winner. Until a supplier is recorded, the correct runtime state is:
> trust store absent, `promotion_allowed: false`, `runtime_status: NOT_RUN`.

## Current state (deterministic)

- `signer_baseline.accepted: true` — R1–R8 are the accepted, provider-neutral source-of-truth.
- `signer_baseline.supplier_selection: NO_SELECTION` — no KMS/HSM/VAULT/PKCS11 product chosen.
- `allows_automatic_supplier_choice: false` under both `LAB_L1` and `PROD`.
- All four candidate classes are `NOT_EVALUATED`; `is_custody_proof: false` for every class,
  including `PKCS11` (interface, not custody).
- `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD`; no campaign observation is resolved
  by this packet.

## Decision criteria (must all hold before a supplier may be recorded)

1. the chosen class must satisfy the accepted R1–R8 baseline (see the requirements doc);
2. the class must be a genuine custody backend for `KMS`/`HSM`/`VAULT` — `PKCS11` alone is never
   sufficient because it is an interface, not custody;
3. the external signer observation must be `OBSERVED` against the approved TB1 descriptor and pass
   `runtime_signer_attestation.verify_signer_attestation` with an injected, verified evidence
   verifier;
4. the explicit public trust store must be declared with path + `key_id` + algorithm + SHA-256 and
   must match the attested `public_key_spki_sha256`;
5. `allows_automatic_supplier_choice` must remain `false`; selection is a recorded human decision.

## Required evidence (per candidate, before any SELECTED state)

- `capability_evidence` recording the provider observation reference (`evidence://…`) and its
  SHA-256, verified by an injected evidence verifier (default verifier refuses everything);
- proof that the private key is non-exportable at the provider (`private_key_exportable == false`);
- proof of `active` key state and `signing_enabled == true`;
- for `PKCS11`: evidence of the concrete token/module *behind* the interface and its custody
  guarantees — the interface alone proves nothing about R1;
- auditability evidence: signing operations are attributable and obtainable without key material.

Missing or unverified evidence fails closed: the evaluation status stays `EVIDENCE_MISSING` or
`EVIDENCE_UNVERIFIED` and the class is disqualified.

## Disqualifiers (fail closed, no auto-recovery)

- `private_key_exportable == true`;
- any secret/private material field present in the attestation;
- `key_id`/`algorithm`/`provider_ref` mismatch with the approved signer binding;
- stale (>5 min) or future observation timestamp;
- unverified or absent source evidence reference/digest;
- `PKCS11` claimed as `is_custody_proof: true` on its own;
- any `evaluation_status: SELECTED` set without a recorded human decision.

## Reversibility / migration considerations

- the descriptor shape is provider-class-neutral (names `provider_kind` among
  `KMS`/`HSM`/`VAULT`/`PKCS11`, never a product), so migrating between custody backends within a
  class does not rewrite descriptors;
- rotation is expressed as trust-store content + expected hash, not ad-hoc file edits;
- LAB_L1-sealed evidence packages are content-addressed and hash-chained, designed to be ingested
  by a future WORM backend without rewriting;
- changing the supplier is a documented decision with provenance, not a silent config change;
- under `PROD`, tenancy and jurisdiction questions remain open and must be decided with the
  supplier choice (shared-infra / data-location).

## Explicit `NO_SELECTION` close

Until a human records an explicit supplier decision referencing this packet and the verified
evidence above, `supplier_selection` stays `NO_SELECTION`. The repository must not infer a winner
from the candidate table, from cost, from availability, or from any other non-security signal.
