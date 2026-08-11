# Evidence Plane backend tenant isolation — provider-neutral acceptance contract

`runtime_evidence_backend_tenant_isolation.py` verifies a normalized observation of multi-tenant isolation controls for a future production Evidence Plane backend. It does not provision tenants, contact storage, mutate access policy or perform backend I/O.

## Identity minimization

The contract never carries customer or tenant names. The two identities used for the negative acceptance are represented only by distinct SHA-256 digests:

- `subject_tenant_sha256`;
- `peer_tenant_sha256`.

A verifier refuses an observation that uses the same digest for both sides.

## Required isolation evidence

An `OBSERVED` envelope passes only when it is fresh, its source evidence is independently verified and all of the following are true:

- tenant namespace isolation is enforced;
- tenant access-policy isolation is enforced;
- tenant encryption context is isolated;
- there is no shared writable evidence namespace;
- cross-tenant listing is `DENIED`;
- cross-tenant reading is `DENIED`;
- cross-tenant writing is `DENIED`.

The source evidence is expected to bind the read-only provider configuration observation and the bounded cross-tenant negative-test results into one custody artefact. The repository verifier does not execute those negative tests itself.

## Provider neutrality

The contract validates isolation properties, not product features. It does not require a particular cloud, object store, appliance, filesystem, identity provider or key-management product.

A future provider-specific collector/harness may normalize live observations into this schema, but the collector and any backend-specific test credentials remain outside this repository boundary.

## Canonical example

`templates/evidence-backend-tenant-isolation-attestation.example.yaml` is deliberately `NOT_RUN`. It uses synthetic digests, has no evidence reference and leaves all negative tests as `NOT_RUN`; it must fail closed.

```bash
python3 deployment/runtime-promotion/runtime_evidence_backend_tenant_isolation.py \
  --attestation deployment/runtime-promotion/templates/evidence-backend-tenant-isolation-attestation.example.yaml \
  --json check
```

## Non-claims

A repository PASS proves only the verifier contract. It does not prove:

- a production Evidence Plane backend is deployed;
- real customer tenants exist in that backend;
- cross-tenant negatives have run live;
- provider configuration/source evidence has been captured live;
- Runner terminal/audit evidence has been persisted live;
- Human-in-the-Loop promotion has occurred.

Even a positive verifier result returns `promotion_allowed=false` and `runtime_status=NOT_RUN` in this repository boundary.

This lane intentionally does not add tenant identity to Evidence Record v2. That would be a separate, cross-cutting schema/version decision and is not required to define the production-backend isolation acceptance gate.

`NO_RUNTIME_CHANGE`.
