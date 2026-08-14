# Lab assurance signer requirements — provider-neutral source-of-truth (Accepted)

**Status:** Accepted — **Decision recorded as R1–R8 provider-neutral signer baseline, 2026-08-14**.
**Classification:** `DECISION / ACCEPTED`. **Decision owners:** `SVP2-A-01`, `EPIC-01`.
**Companion record:** [ADR-0011 — Assurance profiles for the first isolated L1 lab effect](adr/ADR-0011-assurance-profiles-for-first-live-lab-promotion.md).
**Canonical machine-readable binding:** [signer-baseline.schema.json](../../platform/schemas/signer-baseline.schema.json).

This document is the **accepted source-of-truth** for the lab/prod signer requirement set. It is
provider-neutral: it expresses **security properties, never vendor names**. It selects **no vendor,
no provider and no product**. It changes no live policy, no descriptor behaviour and no gate beyond
making the already-approved R1–R8 set testable and binding as the required signer baseline.

> **What acceptance does and does not change.** Accepting R1–R8 formalizes the requirement set as
> the provider-neutral signer baseline. It does **not** select a supplier, create a key, install a
> trust store, enable a policy, or promote any runtime effect. `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`
> remains `BLOCKED / HOLD` with `promotion_allowed: false`, `runtime_status: NOT_RUN` and
> `execution_authority: none`. The technical decision remains `NO_SELECTION` until a human records an
> explicit supplier choice through the decision packet in
> [lab-assurance-signer-decision-packet.md](lab-assurance-signer-decision-packet.md).

## Canonical source-of-truth contract

The prose below is authoritative for semantics. The structured contract is
`signer-baseline.schema.json` (`schema_version: signer-baseline/v1`), which encodes every requirement
as a boolean property on a `signer_baseline` object plus the candidate-class evaluation model. The
verifier `platform/assurance/signer_selection.py` loads the schema and fails closed on any
divergence; `deployment/runtime-promotion/runtime_signer_attestation.py` already validates the live
observation against the approved descriptor (R2, R3, R8) and the
`tb1-signer-attestation.schema.json` envelope (R1, R4, R5, R6).

Provider-neutral requirement ids are stable: `R1` … `R8`. Do not rename, reorder or remove a
requirement once referenced by a change record or an assurance profile.

## Provider-neutral requirements

### R1 — external signer / provider boundary (non-exportable key)

1. the private key is never generated, stored, exported or cached inside this repository or on the
   Runner host (`private_key_local: false`);
2. signing is an operation performed *by* the signer; the caller receives a signature, never key
   material;
3. key destruction and rotation are operations of the signer, auditable independently of the caller.

*Machine check:* `signer_baseline.requires_external_signer` and
`signer_baseline.requires_non_exportable_private_key` are `true`; the attestation envelope requires
`private_key_exportable == false` and `private_key_local == false` in the descriptor.

### R2 — identity and purpose binding

1. one logical, non-secret key identifier is referenced by descriptors;
2. domain `hex0r.tb1.authorization.v1` and purpose `tb1-authorization` are bound to that key;
3. a key valid for another purpose or domain must fail closed, not be reinterpreted.

*Machine check:* descriptor `domain`, `purpose` and `authority` match the canonical TB1 contract; the
observed `key_id`, `provider_ref` and `algorithm` must exactly equal the approved signer binding.

### R3 — verifiable public material (explicit trust store)

1. only public verification material is committed or installed;
2. algorithm is Ed25519 or ECDSA P-256, matching the trust-store entry exactly;
3. the trust store lives under `/etc`, `/run` or `/var/run`, validated against the canonical
   authorization trust-store schema with an expected SHA-256;
4. exactly one active key matches the declared `key_id` and algorithm;
5. the trust store is *explicit*: its path, key id, algorithm and the SHA-256 of the committed
   public material are declared and bound, not inferred.

*Machine check:* `signer_baseline.requires_explicit_trust_store` is `true`; the descriptor trust
store passes `tb1_authorization_preflight.run_preflight`; the attested `public_key_spki_sha256`
equals the SHA-256 of exactly one active trust-store key matching the declared `key_id` and
algorithm.

### R4 — availability and failure semantics

1. signer unavailability yields refusal, never a bypass, a cached authorization or a self-signed
   fallback;
2. timeouts and error codes are explicit and produce `NOT_RUN`/deny, not partial success;
3. no offline signing mode is acceptable for the lab profile.

*Machine check:* attestation `observation_status == OBSERVED` is required for any passed observation;
stale (>5 min) or future timestamps fail closed; `signing_enabled` must be `true` only when the key
is genuinely observed as active.

### R5 — auditability

1. every signing operation is attributable to a principal and a request identity;
2. audit records are obtainable by the operator without exposing key material;
3. absence of an audit record for a signature is a fail-closed condition.

*Machine check:* `signer_baseline.requires_auditability` is `true`; the source provider observation
evidence (`source_evidence_ref` + `source_evidence_sha256`) must be verified by an injected
evidence verifier — the default verifier refuses everything.

### R6 — rotation and revocation (fail-closed)

1. rotation is possible without editing runtime code;
2. revocation of a key invalidates future verification deterministically;
3. rotation is expressed as trust-store content plus expected hash, not as ad-hoc file edits.

*Machine check:* `signer_baseline.requires_revocation_rotation_fail_closed` is `true`; a
revoked/disabled key state fails closed; rotation is represented by trust-store content + expected
digest, never by mutating the descriptor signing path at runtime.

### R7 — operability and cost proportionality

1. bring-up must be reproducible from a documented, non-secret descriptor;
2. the lab profile must not require a hardware procurement cycle to make the boundary testable;
3. the same descriptor shape must remain valid when the production profile uses a stronger backend.

*Machine check:* `signer_baseline.requires_cost_proportional_bring_up` is `true`; the descriptor
shape is provider-class-neutral (it names `provider_kind` among `KMS`/`HSM`/`VAULT`/`PKCS11`, never
a product).

### R8 — evidence separation

1. signer outputs are evidence inputs, not authorization by themselves;
2. no signer configuration, token, session or header is ever written to sanitized evidence.

*Machine check:* `signer_baseline.requires_evidence_separation` is `true`; attestation validation
refuses any secret/private material field and the verifier result never carries key material,
credentials or raw provider responses.

## Candidate classes (evaluation only — no selection)

The candidate-class model (`signer_selection.py` + `signer-baseline.schema.json`) records *capability
evidence* and a *decision status* for the four classes already recognized by the repository:
`KMS`, `HSM`, `VAULT`, `PKCS11`. It **never auto-selects a winner**. Missing or unverified evidence
fails closed. `PKCS11` is an **interface class, not proof of key custody**: it standardizes access
(R2, R6 portability) but asserts nothing about custody strength by itself, so it cannot satisfy R1 on
its own.

| Class | Custody strength | Typical operational cost | Lab bring-up friction | Notes against R1–R8 |
| --- | --- | --- | --- | --- |
| `VAULT` (secrets/transit service) | software isolation, service-mediated signing | moderate | low | satisfies R1–R6 if signing stays server-side; audit quality depends on deployment; needs its own availability story for R4 |
| `KMS` (managed key service) | provider-managed, non-exportable keys | usage-based | low–moderate | strong R1/R5/R6; introduces an external dependency and, in shared deployments, a tenancy question relevant to the `PROD` profile |
| `HSM` | hardware-backed, strongest custody | high (capex/opex) | high | strongest R1; heaviest R7; disproportionate for a first isolated L1 lab effect |
| `PKCS11` (interface, not a product) | depends on the token/module behind it | varies | varies | an *interface* class: it standardizes access (R2, R6 portability) but asserts nothing about custody strength by itself |

`PKCS11` is deliberately listed as an interface class rather than a peer product class, because
choosing it does not answer R1.

## Acceptance, the decision packet and the current state

- R1–R8 are **Accepted** as the provider-neutral signer baseline (`signer_baseline.accepted: true`).
- The technical **supplier selection remains `NO_SELECTION`**. The human decision packet in
  [lab-assurance-signer-decision-packet.md](lab-assurance-signer-decision-packet.md) defines the
  criteria, required evidence, disqualifiers, reversibility/migration considerations and the explicit
  `NO_SELECTION` current state.
- Until a supplier is explicitly selected and recorded, the correct runtime state is the current one:
  trust store absent, promotion refused, `promotion_allowed: false`.

## Why no provider is selected automatically

1. **The requirement set, not the product, is the security property.**
2. **Custody assumptions differ per deployment, not per brand.**
3. **Tenancy and jurisdiction are open** (management/shared-infra and data-location questions belong
   to `PROD`, still undecided).
4. **Cost proportionality is a human trade-off** (R7).
5. **Reversibility** — an early vendor choice creates migration debt in descriptors, audit pipelines
   and runbooks.
6. **Fail-closed default** — until a signer is explicitly bound by an authorized decision, the
   correct state is the current one: trust store absent, promotion refused.

## What this document does not claim

- no provider, product or deployment topology is recommended;
- no key is created, bound, installed or rotated;
- no trust store is created or installed;
- no statement is made that TB1 is satisfiable today;
- no promotion blocker is closed by this document;
- `allows_automatic_supplier_choice` is **false** under both `LAB_L1` and `PROD`.

## Review triggers

Review when: a supplier is selected or explicitly deferred; the external signer or trust-store
availability changes; a WORM or audit-sink backend becomes available; any multi-tenant scenario is
introduced; or the canonical negative test definition changes.
