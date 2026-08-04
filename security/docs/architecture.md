# Consolidated security architecture

## Decision

`pestoura/hermes-security-labs` is the canonical monorepo for the complete authorised security-testing platform.

```text
platform/ = where targets live
security/ = how targets are tested
```

The boundary is deliberate. Laboratory lifecycle code must not depend on a specific runbook pack, and runbooks must not be embedded inside a specific laboratory because one runbook can be exercised against several laboratories or authorised external targets.

## Dependency direction

```text
security campaign
  -> selects runbooks
  -> policy validates scope and risk
  -> binding resolves a registered laboratory
  -> adapter creates a typed request
  -> platform starts the target and attaches Kali temporarily
  -> runner executes an allowlisted profile
  -> evidence is normalised outside Git
  -> platform cleans up and disconnects Kali
```

`security/` may reference laboratory IDs. `platform/` must not import runbook definitions.

## Canonical objects

| Object | Canonical location |
|---|---|
| Laboratory | `platform/environments/**/manifest.yaml` or the current transitional flat manifest |
| Runbook | `security/packs/<domain>/runbooks/**/*.yaml` |
| Campaign | `security/packs/<domain>/campaigns/*.yaml` |
| Adapter catalog | `security/packs/<domain>/adapters/catalog.yaml` |
| Lab-to-pack relationship | `security/bindings/labs.yaml` |
| Generated inventory | disposable output of `securityctl catalog` |

## Current schema generations

The API pack retains its established `ApiPentestRunbook` contract, while DevSecOps and IA/MCP use `SecurityRunbook`. Both are validated in the monorepo. Contract convergence is a separate migration and must not silently rewrite existing semantics.

## Safety invariants

- no free-form shell content in runbooks;
- all target IDs must resolve to the platform catalog;
- production remains deny-by-default;
- no automatic deployment from GitHub to Hermes;
- no self-hosted runner with the Hermes Docker socket;
- no credentials or raw evidence in Git;
- Kali attachment is temporary and ends disconnected;
- runbooks remain experimental until calibrated with positive and negative controls.
