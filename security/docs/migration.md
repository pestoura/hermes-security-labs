# Runbook repository consolidation

## Sources imported

| Component | Source revision | Imported path |
|---|---|---|
| Security Runbook Core | `pestoura/security-runbook-core@54be257bad730d9df3c6b855ca3d453f1fb2b63d` | `security/core/` |
| API Pentest Runbooks | `pestoura/api-pentest-runbooks@3273ec9f8352597758ba2c3f4ddb7ead1e59c926` | `security/packs/api/` |
| DevSecOps Security Runbooks | `pestoura/devsecops-security-runbooks@3588270e9e56f73fe7b7aff46944a1b87d5fde27` | `security/packs/devsecops/` |
| AI/MCP Security Runbooks | `pestoura/ai-mcp-security-runbooks@24078938b2584674f0e075e644677ec1f18b12a9` | `security/packs/ai-mcp/` |

Each source was exported by a temporary same-repository GitHub Actions workflow. The deterministic archive checksum was verified before assembly. No source workflow wrote to another repository.

## Normalisation applied

- repository-local CI workflows and `.gitignore` files were not imported;
- API catalog rows were materialised into 150 individual YAML files and the compressed catalog was removed from the canonical path;
- DevSecOps and IA/MCP provide 120 and 100 individual YAML definitions;
- duplicated laboratory mapping files were replaced by `security/bindings/labs.yaml`;
- campaign category selectors were aligned with the categories that actually exist in each pack;
- top-level cross-pack validation and catalog commands were added;
- source package READMEs retain provenance but point to their canonical monorepo location.

## Repository transition

The old repositories remain available during review. After the consolidated PR is merged and validated on Hermes:

1. close the superseded implementation PRs without merging;
2. add a final README redirect to the canonical monorepo paths;
3. tag the last standalone state;
4. archive the standalone repositories read-only;
5. keep historical issues and PRs for provenance.

No standalone repository should be archived before the consolidated branch passes GitHub CI and exact-head Hermes validation.
