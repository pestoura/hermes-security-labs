# Lab assurance signer — next-decision packet (human supplier choice)

**Status:** Decision packet — **current `supplier_selection: NO_SELECTION`**. This document records
the *deterministic* next step for the future human signer choice. It selects nothing. It is the
companion to [lab-assurance-signer-requirements.md](lab-assurance-signer-requirements.md) (the
accepted R1–R8 baseline) and to the evaluation-only candidate model in
`platform/assurance/signer_selection.py`.

> The technology/product choice remains a separate, explicit human-in-the-loop decision. No code
> path here auto-selects a winner. A human decision may be approved while the baseline still stays
> `NO_SELECTION`; that staged state grants no trust binding, runtime execution or promotion.

## Current state (deterministic)

- `signer_baseline.accepted: true` — R1–R8 are the accepted, provider-neutral source-of-truth.
- `signer_baseline.supplier_selection: NO_SELECTION` — no KMS/HSM/VAULT/PKCS11 product chosen.
- `signer_baseline.selected_class: null` and `human_decision_id: null` make the current absence of
  selection explicit and machine-checkable.
- `platform/assurance/signer-human-decision.yaml` is the explicit human-decision source-of-truth
  and is currently `state: NO_DECISION`, with no selected class and no evidence references.
- `platform/schemas/signer-human-decision.schema.json` and
  `platform/assurance/signer_human_decision.py` enforce the repository-only decision contract:
  an `APPROVED` record may name only `KMS`, `HSM` or `VAULT`, must bind the required evidence
  classes by canonical `evidence://` references plus SHA-256, and still grants no promotion.
- CHG-HSL-063 explicitly permits that `APPROVED` record to be staged while the baseline remains
  `NO_SELECTION`; `selected_class` and `human_decision_id` remain null until a separate transition.
- `platform/assurance/signer_selection.py::validate_selection_transition_contract` is the
  CHG-HSL-063 consistency gate. A future `PENDING`/`SELECTED` state is accepted as internally
  coherent only when `selected_class` and `human_decision_id` match that APPROVED human decision
  and the same candidate already has verified custody evidence.
- CHG-HSL-063 deliberately keeps trust binding inactive for the current state, for an APPROVED
  staged decision, and even for a coherent selection contract; selection does not imply trust
  installation or runtime/promotion authority.
- `allows_automatic_supplier_choice: false` under both `LAB_L1` and `PROD`.
- All four committed candidate classes are `NOT_EVALUATED`; `is_custody_proof: false` for every
  class, including `PKCS11` (interface, not custody).
- `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD`; no campaign observation is resolved
  by this packet, an `APPROVED` decision record, or a coherent selection contract alone.

## Decision and transition sequence

The intended sequence is deliberately staged rather than implicit or automatic:

1. `NO_DECISION + NO_SELECTION` — current state; no class chosen and no authority granted;
2. `APPROVED + NO_SELECTION` — a human choice has been recorded with evidence references, but the
   signer baseline is still unbound (`selected_class: null`, `human_decision_id: null`), trust is
   inactive and runtime remains `NOT_RUN`;
3. `APPROVED + PENDING/SELECTED` — a separate governed change binds the exact human decision ID and
   selected custody class after the matching candidate has verified custody evidence;
4. trust binding and any live promotion remain separate later changes with independent evidence,
   validation and approval.

There is no valid path that collapses these stages into an automatic provider choice or turns a
human decision into implicit runtime authority.

## Decision criteria (must all hold before a supplier may be recorded)

1. the chosen class must satisfy the accepted R1–R8 baseline (see the requirements doc);
2. the class must be a genuine custody backend for `KMS`/`HSM`/`VAULT` — `PKCS11` alone is never
   sufficient because it is an interface, not custody;
3. the external signer observation must be `OBSERVED` against the approved TB1 descriptor and pass
   `runtime_signer_attestation.verify_signer_attestation` with an injected, verified evidence
   verifier;
4. the explicit public trust store must be declared with path + `key_id` + algorithm + SHA-256 and
   must match the attested `public_key_spki_sha256`;
5. `allows_automatic_supplier_choice` must remain `false`; selection is a recorded human decision;
6. the human decision must be recorded through the CHG-HSL-062 contract and bind, at minimum,
   `capability_evidence`, `signer_attestation`, `trust_store_manifest` and `r1_r8_review` evidence;
7. any future baseline `PENDING`/`SELECTED` state must carry the exact `selected_class` and
   `human_decision_id`, and the matching candidate must be
   `EVIDENCE_VERIFIED_PENDING_DECISION`, have `is_custody_proof: true`, and carry a non-null
   capability-evidence record;
8. that selection-state transition still leaves `trust_binding` disabled/null until a separate,
   explicit trust-binding change is approved and validated.

## Required evidence (per candidate, before any SELECTED state)

- `capability_evidence` recording the provider observation reference (`evidence://…`) and its
  SHA-256, verified by an injected evidence verifier (default verifier refuses everything);
- proof that the private key is non-exportable at the provider (`private_key_exportable == false`);
- proof of `active` key state and `signing_enabled == true`;
- for `PKCS11`: evidence of the concrete token/module *behind* the interface and its custody
  guarantees — the interface alone proves nothing about R1;
- auditability evidence: signing operations are attributable and obtainable without key material;
- a trust-store manifest and R1–R8 review bound into the human decision record by canonical
  evidence references and exact SHA-256 digests.

Missing or unverified evidence fails closed: the evaluation status stays `EVIDENCE_MISSING` or
`EVIDENCE_UNVERIFIED` and the class is disqualified. A syntactically valid human decision record
is not evidence verification and does not replace any canonical signer/trust/promotion verifier.

## Disqualifiers (fail closed, no auto-recovery)

- `private_key_exportable == true`;
- any secret/private material field present in the attestation;
- `key_id`/`algorithm`/`provider_ref` mismatch with the approved signer binding;
- stale (>5 min) or future observation timestamp;
- unverified or absent source evidence reference/digest;
- `PKCS11` claimed as `is_custody_proof: true` on its own or selected as the custody backend;
- any `evaluation_status: SELECTED` set without a recorded human decision;
- any `APPROVED` human decision missing one of the four required evidence classes, containing
  duplicate evidence classes, or using non-canonical refs/digests;
- a baseline `selected_class` or `human_decision_id` that differs from the approved human record;
- a selected candidate that has not already reached verified-evidence/custody state;
- any attempt to turn on `trust_binding` as a side effect of a staged decision or supplier
  selection.

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

Before a human decision exists, `supplier_selection` stays `NO_SELECTION`, `selected_class` and
`human_decision_id` stay `null`, and `platform/assurance/signer-human-decision.yaml` stays
`NO_DECISION`. The repository must not infer a winner from the candidate table, from cost, from
availability, or from any other non-security signal.

Once the human decision is explicitly `APPROVED`, the baseline may **still remain `NO_SELECTION`**
while the separate governed transition is prepared. In that staged state, `selected_class` and
`human_decision_id` in the baseline remain null, `trust_binding` stays inactive,
`promotion_allowed` stays false and runtime stays `NOT_RUN`.

CHG-HSL-063 provides the deliberate transition guard that CHG-HSL-062 intentionally left
separate: it can validate a future human-selected `PENDING`/`SELECTED` contract, but it **does not
make the decision**, does not bind trust, and always returns `promotion_allowed: false` /
`runtime_status: NOT_RUN`. Trust-store installation and live promotion remain later, separately
approved gates.
