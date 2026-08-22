# CHG-HSL-088 implementation plan

1. Add RED tests for the dedicated receipt-delivery runtime package, listener,
   peer identity boundary, bounded framing, systemd units and fail-closed deployment.
2. Verify RED is caused by missing CHG-HSL-088 capability rather than test defects.
3. Implement the minimum listener and deployment artifacts needed for GREEN.
4. Reuse canonical `unix_peer_identity.py` and `receipt_delivery.py`; do not duplicate
   SO_PEERCRED or receipt verification logic.
5. Harden framing, timeouts, response sanitization, service restrictions, drift
   detection and rollback behavior.
6. Run focused tests, affected regression, then full repository regression.
7. Run `make validate`, canonical lint, diff checks and secret scan.
8. Create CHG-HSL-088 record only after evidence exists; commit and open PR.
9. Require all protected workflows plus Exact-SHA validation on final PR head.
10. Squash merge with expected-head protection and verify merged main on HermesJarvas.
11. Only after merge, attempt the safe live endpoint deployment/proof. Never enable
    receipt acceptance without the later trust/policy gate; record any root/HITL
    requirement as an explicit blocker rather than weakening host permissions.