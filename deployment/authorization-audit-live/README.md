# Authorization-audit live persistence probe

CHG-HSL-090 provides a bounded synthetic runtime proof for the existing authorization-audit custody path.

It composes the canonical `CanonicalAuthorizationAuditAdapter`, `AuthorizationAuditCustody`, `LocalEvidenceStore`, `LocalEvidenceVerifier` and `AuditSink` on HermesJarvas.

Safety properties:

- the committed custody policy must remain `DISABLED / NOT_RUN`;
- the probe enables only an in-memory policy copy;
- only one synthetic sanitized authorization event is persisted;
- the store is reopened and integrity is verified before success;
- raw authorization references are not returned by the probe;
- no receipt delivery, resolver trust, signer, Vault or target effect is created;
- `execution_authority=NONE` and `promotion_allowed=false` remain invariant;
- the probe refuses a pre-existing root and removes only the root it created.

After merge, run from the repository root with a fresh disposable path:

```bash
python3 deployment/authorization-audit-live/probe.py --root /tmp/hsl-chg090-live-proof
```

A successful run emits only sanitized JSON and removes the disposable store before exit.
