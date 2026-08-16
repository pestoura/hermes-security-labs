# CHG-HSL-076 — Signer Audit EvidenceVerifier Linkage Plan

**Goal:** Persist the public `signer-operation-audit/v1` event through the existing Evidence Plane store and bind its exact content into the existing AuditSink through a canonical `EvidenceVerifier` reference, with zero provider/runtime/trust authority.

## Constraints

- Canonical policy is `DISABLED`, `runtime_status=NOT_RUN`, `execution_authority=none`.
- No provider client, network, subprocess, trust installation, key provisioning or Runner/target effect.
- No second datastore, EvidenceChain, seal or verifier implementation.
- The custody bridge receives an injected existing Evidence Plane store; it never instantiates `LocalEvidenceStore`.
- Persisted payload is only canonical JSON of the already-public CHG-HSL-075 audit event; never original signing payload or raw signature/base64.
- `NO_DECISION / NO_SELECTION` in #403 remains unchanged.

## Tasks

1. Add failing tests for a disabled canonical custody policy, event/schema validation, canonical persistence, idempotent replay, safe backend failures, and no-runtime/no-parallel-store static guards.
2. Add failing integration tests proving `LocalEvidenceVerifier.verify(evidence_ref, payload_sha256)` and `AuditSink.verify(resolver=...)` linkage.
3. Implement `platform/evidence-plane/signer_audit_custody.py` and a disabled `signer-audit-custody-policy.yaml`, reusing `evidence_plane.build_record` and injected store `put/verify` methods.
4. Extend `CanonicalSignerAuditAdapter.record_signing` with an optional canonical `evidence_ref` passed to the existing AuditSink. Preserve the no-evidence-ref CHG-HSL-075 path unchanged.
5. Add CHG-HSL-076 governance/architecture documentation and update the provider-neutral signer roadmap to mark audit-event/EvidenceVerifier linkage complete while retaining all operational blockers.
6. Validate focused tests, full repository CI on exact PR head, review, squash merge, then validate all push workflows including Exact-SHA on the new main SHA.
