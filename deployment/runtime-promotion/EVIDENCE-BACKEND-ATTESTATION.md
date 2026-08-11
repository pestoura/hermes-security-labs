# Evidence Plane durable backend attestation — provider-neutral acceptance contract

`runtime_evidence_backend_attestation.py` verifies a normalized, read-only observation of the controls exposed by a future production Evidence Plane backend. It does **not** implement or select that backend.

## Repository capability

An `OBSERVED` envelope passes only when all of the following are true:

- the observation is fresh and scoped to `PRODUCTION`;
- the backend reports state `active`;
- encryption at rest is enforced;
- immutability is `WORM_COMPLIANCE` rather than governance/bypass mode;
- retention enforcement is active;
- legal hold is supported;
- privileged delete bypass is unavailable;
- public access is blocked;
- versioning is enabled;
- SHA-256 remains the integrity digest;
- an independently injected `EvidenceVerifier` confirms the source provider-metadata artefact at the declared `evidence://` reference and SHA-256.

The default evidence verifier denies everything, so a committed YAML file cannot become acceptance evidence by presence alone.

## Provider neutrality

This boundary contains no client or provisioning code for AWS, Azure, Google Cloud, S3-compatible products, appliances or filesystems. A future provider-specific collector may normalize read-only configuration metadata into the common schema, but provider selection and deployment are separate decisions.

The contract intentionally validates capabilities rather than product names.

## Canonical example

`templates/evidence-backend-attestation.example.yaml` is deliberately `NOT_RUN` and deliberately fails the production control requirements. It is a schema/example artefact only.

```bash
python3 deployment/runtime-promotion/runtime_evidence_backend_attestation.py \
  --attestation deployment/runtime-promotion/templates/evidence-backend-attestation.example.yaml \
  --json check
```

The command must return a fail-closed result for the committed example.

## Non-claims

A repository PASS for this verifier does not prove any production backend exists or is connected to the Runner. Even a future positive `OBSERVED` attestation does not by itself prove:

- live Runner → Evidence Plane handoff;
- live dispatch-audit or terminal-outcome persistence;
- tenant isolation;
- a retention expiry/deletion operation;
- production redaction/reconstruction;
- customer export;
- Human-in-the-Loop promotion.

The existing `LocalEvidenceStore` remains the controlled CI reference store and is not reclassified as WORM or production durable storage.

`NO_RUNTIME_CHANGE`.
