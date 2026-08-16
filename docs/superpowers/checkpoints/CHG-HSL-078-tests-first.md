# CHG-HSL-078 tests-first checkpoint

- Branch: `chg-hsl-078/authorization-receipt-audit`
- Base: `5f9440fa73b057390c024c601645b3e10c511300`
- Decision: ADR-0015 / Option 3 selected
- Production adapter/schema: intentionally absent at this checkpoint
- Tests-first contract: `platform/tests/test_authorization_receipt_audit_adapter.py`
- Expected CI state: RED only because `authorization_audit_adapter.py` and/or its schema are not implemented yet
- Runtime policies: unchanged and disabled
- Execution authority: none
- Promotion authority: false
