# EPIC-35 — SDK, plugins and runtime certification

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-35` |
| Slug | `sdk-plugins-and-runtime-certification` |
| Pillar | `K` — SDK and Extensibility |
| Phase | 6 |
| Priority | P2 |
| Delivery umbrella | `SVP2-K-01` (issue [#95](https://github.com/pestoura/hermes-security-labs/issues/95)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #147 integrated a repository-owned extension manifest, conformance/certification decision contract and adversarial tests for five extension families. The repository now has concrete fail-closed activation-eligibility primitives, but production signature verification, extension loading, runtime isolation, production certification and third-party extension execution remain `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Extending the platform with new runners, labs or knowledge sources has no supported contract, conformance kit or certification path.

## 4. Intended outcome

Extension SDKs with a conformance kit, permission manifests, signing and a certification process before an extension may run.

## 5. Scope and non-goals

### In scope

- SDK surface per extension type
- Conformance kit exercising protocol invariants
- Permission manifest declaring required capabilities
- Signing and certification levels

### Non-goals

- Accepting unsigned third-party extensions at runtime

## 6. Intent architecture

An extension declares permissions; the gateway grants only the intersection of manifest, capability registry and active contract.

## 7. Contracts, data and capabilities

PR #147 introduced repository-owned candidates under `platform/extensions/`:

- `extension-manifest.schema.json`;
- `extension-policy.yaml`;
- `conformance.py`;
- `README.md`;
- conformance tests in `platform/tests/test_extension_conformance.py`.

The contract recognizes five extension families:

- Capability Runner;
- Runtime Driver;
- Lab Driver;
- Evidence Adapter;
- Evaluator.

The manifest contract requires explicit permissions from a bounded allowlist, compatibility evidence, conformance evidence, signature-verification evidence and a controlled lifecycle state. Command-shaped execution fields such as `command`, `argv`, `shell`, `cwd`, `environment`, `executable` and `entrypoint` are rejected.

Certification is a deterministic decision over supplied evidence. It is **not** a production cryptographic signature-verification implementation and it does not load or execute an extension.

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-05 — Runner Protocol v2](EPIC-05-runner-protocol-v2.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

The repository contract is dependency-safe because it consumes protocol/registry concepts without activating any runtime extension path.

## 9. Security, risks and failure modes

- Extensions requesting excessive permissions
- Conformance kit lagging protocol changes
- Treating externally supplied `verified` signature evidence as cryptographic verification performed by this component
- Treating certification or activation eligibility as execution authorization
- Allowing a manifest to smuggle command-shaped execution data

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- Hermes / Control Plane remains the sole authority that may grant execution authorization;
- an extension manifest, certification decision or `activation_allowed=true` result never creates, grants or expands an `authorization_ref`;
- granted runtime permissions, when that runtime path is implemented, must be an intersection and never exceed the declared manifest;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

Repository candidate delivered by PR #147:

- strict extension manifest schema;
- five fixed extension-family identifiers;
- bounded explicit permission vocabulary;
- deterministic conformance/certification eligibility logic;
- quarantine, deprecation and revocation fail-closed semantics;
- compatibility and conformance evidence binding;
- externally supplied signature-verification evidence gate;
- positive, negative and adversarial conformance tests.

Still pending:

- concrete SDK interfaces/implementations used by runtime extensions;
- production cryptographic signature verification;
- extension package loading/import lifecycle;
- runtime sandbox/isolation enforcement;
- gateway enforcement of the effective permission intersection across manifest, capability registry and active authorization contract;
- production certification service/process and operational revocation propagation;
- third-party extension execution.

## 11. Acceptance criteria

Repository-level evidence currently demonstrates:

- candidate, quarantined, deprecated and revoked extensions are not activation-eligible;
- certification requires supplied verified-signature evidence, protocol compatibility and passing conformance evidence;
- permissions must be explicit, unique and drawn from the bounded allowlist;
- command-shaped execution fields are refused;
- quarantine and revocation fail closed.

Epic acceptance is **not yet complete** because:

- no extension is actually loaded or refused by a production runtime;
- the runtime permission grant/intersection path does not yet exist, so the invariant that granted permissions never exceed the manifest has not been demonstrated in execution;
- production signature verification and production certification remain `NOT_RUN`.

## 12. Evidence and validation plan

Current repository evidence:

- technical implementation: PR #147;
- `platform/tests/test_extension_conformance.py` exercises all five extension families, certification gates, bounded permissions, forbidden execution fields, quarantine/revocation and runtime non-claims;
- repository `security` and `validate` gates are mandatory for lifecycle reconciliation.

Operational evidence for extension loading, sandboxing, signature verification, effective permission enforcement and third-party execution remains `NOT_RUN`.

## 13. Decisions and open questions

### Decisions

- Permission grants are intersections, never unions.
- Certification/activation eligibility is not execution authorization.
- Hermes / Control Plane remains the sole execution-authorization authority.
- Externally supplied signature-verification evidence is sufficient only for the repository contract candidate; it is not a claim that this component performs cryptographic verification.
- Command-shaped generic execution fields are forbidden in extension manifests.
- Quarantined, deprecated and revoked extensions fail closed.

### Open questions

- Whether internal extensions require the same certification level
- Concrete SDK API stability/versioning policy per extension family
- Trust-store and signer lifecycle for production extension verification
- Runtime sandbox boundaries per extension family
- Operational revocation propagation and cache invalidation

## 14. Implementation notes

> Reserved lifecycle section. It is populated progressively while the epic is `IMPLEMENTING`; retaining the `Reserved` marker is required by the architecture documentation lifecycle contract.

- PR #147 (`feat(svp2-k-01): add extension SDK conformance contract`) introduced the current repository-owned contract candidate.
- `validate_manifest()` fails closed for unsupported kinds/lifecycle states, unknown/duplicate permissions, incomplete signature/compatibility/conformance evidence and command-shaped fields.
- `activation_failures()` requires verified supplied signature evidence, declared compatibility, a passing conformance report and lifecycle `certified`.
- `certify()` refuses quarantined/revoked/deprecated inputs and only produces `certified` when the deterministic gates pass.
- `quarantine()` and `revoke()` make the extension non-activation-eligible.
- No extension package is imported, loaded, sandboxed or executed.
- No runtime permission is granted by this component.
- No execution authorization is minted or expanded; Hermes / Control Plane remains the sole authority.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved lifecycle section. This section records the current implementation boundary but remains non-final while the epic is `IMPLEMENTING`.

Current factual boundary:

- five extension families: repository contract candidate;
- extension manifest schema: repository implemented/tested;
- explicit bounded permission declaration: repository implemented/tested;
- compatibility/conformance evidence gates: repository implemented/tested;
- externally supplied signature-verification evidence gate: repository implemented/tested;
- deterministic certification and activation-eligibility decision: repository implemented/tested;
- quarantine/deprecation/revocation refusal semantics: repository implemented/tested;
- concrete runtime SDK implementations: `NOT_IMPLEMENTED`;
- production cryptographic signature verification: `NOT_RUN`;
- extension loading/import: `NOT_RUN`;
- runtime isolation/sandbox enforcement: `NOT_RUN`;
- production effective permission-intersection enforcement: `NOT_IMPLEMENTED` / `NOT_RUN`;
- production certification: `NOT_RUN`;
- third-party extension execution: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.

`AS_BUILT` and `FINAL` remain false.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-07 | 1.1.0 | Reconciled PR #147 extension contract candidate to `IMPLEMENTING`; recorded authority, permission-enforcement and runtime non-claims. |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
