# Lab assurance signer requirements — provider-neutral analysis (proposal)

**Status:** Em validação / EM_VALIDACAO — **non-final, non-operative**. This document selects **no
vendor, no provider and no product**. It changes no policy, no descriptor, no template and no gate.
`VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD` with `promotion_allowed: false`,
`runtime_status: NOT_RUN` and `execution_authority: none`.

Companion record: [ADR-0011 — Assurance profiles for the first isolated L1 lab effect](adr/ADR-0011-assurance-profiles-for-first-live-lab-promotion.md).

## Purpose

The TB1 authorization chain requires an **external** signer and a purpose-bound **public** trust
store at the Runner. The repository can already validate that declaration statically
(`deployment/runtime-promotion/tb1_authorization_preflight.py`), and the current live finding is that
the Runner authorization trust store is **ABSENT**. What is missing is not a product choice but an
explicit, testable requirement set. This document writes that requirement set down, provider-neutral.

## Provider-neutral requirements

### R1 — key custody

1. the private key is never generated, stored, exported or cached inside this repository or on the
   Runner host (`private_key_local: false`);
2. signing is an operation performed *by* the signer; the caller receives a signature, never key
   material;
3. key destruction and rotation are operations of the signer, auditable independently of the caller.

### R2 — identity and purpose binding

1. one logical, non-secret key identifier is referenced by descriptors;
2. domain `hex0r.tb1.authorization.v1` and purpose `tb1-authorization` are bound to that key;
3. a key valid for another purpose or domain must fail closed, not be reinterpreted.

### R3 — verifiable public material

1. only public verification material is committed or installed;
2. algorithm is Ed25519 or ECDSA P-256, matching the trust-store entry exactly;
3. the trust store lives under `/etc`, `/run` or `/var/run`, validated against the canonical
   authorization trust-store schema with an expected SHA-256;
4. exactly one active key matches the declared `key_id` and algorithm.

### R4 — availability and failure semantics

1. signer unavailability yields refusal, never a bypass, a cached authorization or a self-signed
   fallback;
2. timeouts and error codes are explicit and produce `NOT_RUN`/deny, not partial success;
3. no offline signing mode is acceptable for the lab profile.

### R5 — auditability

1. every signing operation is attributable to a principal and a request identity;
2. audit records are obtainable by the operator without exposing key material;
3. absence of an audit record for a signature is a fail-closed condition.

### R6 — rotation and revocation

1. rotation is possible without editing runtime code;
2. revocation of a key invalidates future verification deterministically;
3. rotation is expressed as trust-store content plus expected hash, not as ad-hoc file edits.

### R7 — operability and cost proportionality

1. bring-up must be reproducible from a documented, non-secret descriptor;
2. the lab profile must not require a hardware procurement cycle to make the boundary testable;
3. the same descriptor shape must remain valid when the production profile uses a stronger backend.

### R8 — evidence separation

1. signer outputs are evidence inputs, not authorization by themselves;
2. no signer configuration, token, session or header is ever written to sanitized evidence.

## Candidate classes (no selection)

| Class | Custody strength | Typical operational cost | Lab bring-up friction | Notes against R1–R8 |
| --- | --- | --- | --- | --- |
| `VAULT` (secrets/transit service) | software isolation, service-mediated signing | moderate | low | satisfies R1–R6 if signing stays server-side; audit quality depends on deployment; needs its own availability story for R4 |
| `KMS` (managed key service) | provider-managed, non-exportable keys | usage-based | low–moderate | strong R1/R5/R6; introduces an external dependency and, in shared deployments, a tenancy question relevant to the `PROD` profile |
| `HSM` | hardware-backed, strongest custody | high (capex/opex) | high | strongest R1; heaviest R7; disproportionate for a first isolated L1 lab effect |
| `PKCS11` (interface, not a product) | depends on the token/module behind it | varies | varies | an *interface* class: it standardizes access (R2, R6 portability) but asserts nothing about custody strength by itself |

`PKCS11` is deliberately listed as an interface class rather than a peer product class, because
choosing it does not answer R1.

## Why no provider should be chosen automatically

1. **The requirement set, not the product, is the security property.** Selecting a vendor before
   R1–R8 are accepted would freeze an implementation around unstated assumptions.
2. **Custody assumptions differ per deployment, not per brand.** The same class can be strong or
   weak depending on how it is operated; only R1–R8 make that difference visible.
3. **Tenancy and jurisdiction are open.** Managed services introduce shared-infrastructure and data
   location questions that belong to the `PROD` profile decision, still undecided.
4. **Cost proportionality is a human trade-off.** R7 weighs procurement and operating cost against
   the value of testing one isolated L1 boundary; that is Pedro's decision, not an automatic one.
5. **Reversibility.** An early vendor choice creates migration debt in descriptors, audit pipelines
   and operator runbooks; keeping the descriptor provider-neutral preserves reversibility.
6. **Fail-closed default.** Until a signer is explicitly bound by an authorized decision, the
   correct state is the current one: trust store absent, promotion refused.

## What is explicitly not claimed here

- no provider, product or deployment topology is recommended;
- no key is created, bound, installed or rotated;
- no trust store is created or installed;
- no statement is made that TB1 is satisfiable today;
- no promotion blocker is closed by this document.

## Human decision required

Accept or reject R1–R8 as the provider-neutral requirement baseline, and only then evaluate
candidate classes against it. Until that decision is recorded, the signer blocker stays open.
