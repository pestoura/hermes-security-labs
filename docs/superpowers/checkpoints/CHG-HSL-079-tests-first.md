# CHG-HSL-079 — Tests-first RED checkpoint

- **Branch:** `chg-hsl-079/authorization-audit-evidence-custody`
- **Pull request:** #417
- **Exact branch head:** `837bcf845d0d0b2128eb347ef79c12269882092a`
- **GitHub Actions validate run:** `31927740965`
- **PR test merge SHA:** `e5bffd15eb71104cb751086bd8c9029c07ede4ea`
- **Observed:** 2026-08-16
- **Phase:** tests-first RED before production custody implementation

## Preconditions

The first PR run was blocked by ADR governance defects before reaching the intended test. Those defects were corrected first: ADR-0016 now contains the canonical mandatory sections and is indexed in `docs/architecture/adr/README.md`.

On exact branch head `837bcf845d0d0b2128eb347ef79c12269882092a` the preconditions were GREEN:

- documentation tests: `1099 passed`;
- JDS aggregate static walking-skeleton gate: PASS;
- Runner Protocol v2 SDK, contract and conformance kit: PASS;
- Security catalog, packs and lint: PASS;
- Compose, lifecycle and Phase 2 runtime gates: PASS;
- runtime source-of-truth validation: PASS.

## RED evidence

Command executed by the canonical `validate` workflow:

```text
python -m pytest -q platform/tests -p no:cacheprovider
```

Observed result:

```text
13 failed, 2281 passed, 7 skipped in 149.34s
```

All 13 failures are confined to:

```text
platform/tests/test_authorization_audit_evidence_custody.py
```

Every failure reaches the same deliberate missing-capability assertion:

```text
AssertionError: authorization_audit_custody.py is not implemented yet
```

The missing file is:

```text
platform/evidence-plane/authorization_audit_custody.py
```

No unrelated platform regression was observed.

## TDD decision

The required RED state is therefore valid and specific: tests prove the authorization-audit Evidence Plane custody capability is absent before production implementation.

Production custody module and committed policy were not present at this checkpoint. Implementation may now proceed to the minimum GREEN defined by ADR-0016 and the CHG-HSL-079 implementation plan.

This checkpoint creates no runtime or execution authority. Receipt delivery/resolver policy remains disabled, no target effect is authorized, and the live promotion campaign remains `BLOCKED / HOLD`.
