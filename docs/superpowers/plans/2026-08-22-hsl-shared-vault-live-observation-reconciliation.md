# CHG-HSL-087 implementation plan

1. Add a focused repository test for the reconciled shared-Vault live state.
2. Run the test RED against the stale walking-skeleton/campaign documents.
3. Update `docs/roadmap/current-walking-skeleton-status.md` with the accepted CHG-HSL-085/086 path and pre-Secret-Zero observation.
4. Update `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` evidence text while preserving `BLOCKED/HOLD` and all downstream NOT_RUN states.
5. Add `changes/CHG-HSL-087.yaml` with runtime validation `PASS` for the bounded observation only.
6. Re-run the focused test GREEN.
7. Run docs, campaign, JDS/source-of-truth and change-record regression gates.
8. Run `make validate`, canonical lint and relevant full regression.
9. Verify no signer decision, baseline, trust or policy authority files changed.
10. Commit, push, open PR, link the PR in the change record and validate exact-head CI.
11. Merge only when all protected exact-SHA workflows are SUCCESS.
12. Post-merge verify `main`, then update issues #403/#426 with the reconciled state.

## Runtime rule

This plan performs no Secret Zero operation. The live probe may be read only for sanitized health/topology confirmation. Any step that handles AppRole bootstrap credentials remains a separate HITL boundary.