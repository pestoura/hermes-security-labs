## Summary

Repository-only Lane 1 (LAB_L1) after ADR-0011 Option B. Implements the foundational tamper-evident content-addressed evidence chain + seal that ADR-0011 Option B keeps for LAB_L1.

This is a strict subset / migration-compatible input to the future PROD WORM ingestion contract (ADR-0011 migration path item 2). The seal binds chain state with a hash only — no signing key.

## Scope (additive, fail-closed)

- Immutable content-addressed objects remain canonical.
- Each chain entry deterministically binds: record/object digest, previous entry digest (or explicit genesis null), monotonically ordered chain index, evidence/correlation identifiers, and deterministic canonical serialization.
- Seal/envelope hashes/binds chain state without a private signing key. `bindings.signer=null`, `authenticity=false`, `durability=false`.
- Fails closed on malformed linkage, index discontinuity, digest mismatch, tampering, replay/reordering, or missing referenced object.
- No mutable overwrite of prior entries. Reuses `LocalEvidenceStore` and `evidence_plane` canonical serialization.

## Deliverables

- `platform/evidence-plane/evidence_chain.py`
- `platform/evidence-plane/seal.py`
- `platform/schemas/evidence-chain.schema.json`
- `platform/tests/test_lab_l1_evidence_chain_seal.py` (34 tests)

## Governance

- Change record: `CHG-HSL-042` (DOC_ONLY, FAIL_CLOSED, promotion_allowed false).
- Linked to observation `OBS-EVIDENCE-CUSTODY` without claiming it resolved.
- Campaign `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` and runtime policies remain BLOCKED / HOLD; `promotion_allowed=false`.
- No live mutation, key/trust/provider creation, Docker, or target interaction.

## Non-claims

The hash seal is NOT a signer and NOT a WORM backend. It provides integrity / tamper-evidence only. External authenticity and durability remain PROD-only properties.
