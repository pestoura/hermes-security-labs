# Superseded repositories

This document is the canonical record of the standalone repositories that were
consolidated into `pestoura/hermes-security-labs`. It closes the consolidation
block accepted in issue #63 (main `4448b80df3a670d5c4454711640b0aabe2a5b597`).

## Policy

- The monorepo is the only place where security packs, the runbook core, the
  laboratory bindings and the campaigns are changed.
- Superseded repositories are archived read-only. Their history, branches,
  tags, releases, issues and pull requests stay available for provenance.
- Nothing is deleted or rewritten in the superseded repositories.
- New contributions must be made in this repository, never in an archived one.

## Consolidated repositories

| Repository | Last standalone `main` SHA | Imported revision | Canonical path | Tags / releases | Consolidated |
|---|---|---|---|---|---|
| `pestoura/security-runbook-core` | `54be257bad730d9df3c6b855ca3d453f1fb2b63d` | `54be257bad730d9df3c6b855ca3d453f1fb2b63d` | `security/core/` | none | 2026-08-05 |
| `pestoura/api-pentest-runbooks` | `43facd1afefc4197576a96af228207798b7cdb63` | `3273ec9f8352597758ba2c3f4ddb7ead1e59c926` | `security/packs/api/` | none | 2026-08-05 |
| `pestoura/devsecops-security-runbooks` | `169c9b8e3ac1026567598c26b82c68d45ef26609` | `3588270e9e56f73fe7b7aff46944a1b87d5fde27` | `security/packs/devsecops/` | none | 2026-08-05 |
| `pestoura/ai-mcp-security-runbooks` | `9c1017d3975e98a67c779afab91931e99282f042` | `24078938b2584674f0e075e644677ec1f18b12a9` | `security/packs/ai-mcp/` | none | 2026-08-05 |

No repository had tags, releases or published packages, so no artefact
reference required preservation beyond the commit SHAs above.

## Equivalence evidence

Runbook identifier coverage was recomputed from the exported migration
branches against the canonical packs:

| Pack | Identifiers in the standalone repository | Present in the monorepo | Missing |
|---|---:|---:|---:|
| api | 150 | 150 | 0 |
| devsecops | 120 | 120 | 0 |
| ai-mcp | 100 | 100 | 0 |

`securityctl validate` reports `api=150 devsecops=120 ai-mcp=100 total=370
warnings=0`.

Files that differ from the standalone snapshots are the ones deliberately
normalised or improved after import: repository-local CI workflows and
`.gitignore` files were not imported, duplicated laboratory manifests were
replaced by `security/bindings/labs.yaml`, compressed catalogs were
materialised into individual YAML runbooks, and the runners, adapters and
evaluation contracts were calibrated in this repository after the campaigns for
crAPI, WrongSecrets and PromptMe. The monorepo content is therefore a superset
of the standalone content; no exclusive or more recent behaviour remains only
in the old repositories.

See also [`security/docs/migration.md`](../../security/docs/migration.md) for
the import procedure and the normalisation rules.

## Open issues and pull requests

The superseded repositories keep open planning issues and unmerged
implementation pull requests from the pre-consolidation phase. They are not
deleted and not merged: the work they describe was delivered in this
repository. Each repository receives a final migration issue that links to this
document, and their pull requests remain closed to change but readable.

## Contributing after consolidation

1. Open an issue or pull request in `pestoura/hermes-security-labs`.
2. Change the pack under `security/packs/<pack>/` or the engine under
   `security/core/`.
3. Run `python3 security/tools/securityctl.py validate` and the pack tests.
4. Never reopen or unarchive a superseded repository to land a change.
