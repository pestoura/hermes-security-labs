# Capability Registry and Promotion — contract candidate

Repository-owned contract candidate for `SVP2-C-02`.

## Implemented guarantees

A capability is usable as `stable` only when all of the following are true:

- installed;
- executable;
- functionally tested;
- explicitly authorized by policy;
- protocol-compatible;
- SBOM reference present;
- signature reference present;
- provenance reference present;
- zero blocking scan findings;
- not quarantined or revoked.

Revocation makes a capability immediately unusable. A quarantined capability cannot be promoted directly to stable. Unknown profiles fail closed.

## Profiles

`web-api`, `devsecops`, `ai-mcp`, `exploitation`, `kubernetes`, `identity`, `cloud`, `mobile`, `iot-ot`.

## Deliberate non-claims

This block does not generate SBOMs, sign artefacts, generate SLSA provenance, scan images, publish images or exercise production revocation. Those gates are represented by evidence references and remain `NOT_RUN` until the image factory and runtime integrations exercise them.

`NO_RUNTIME_CHANGE`.
