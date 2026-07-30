# Catalog layout

## Current convention
- Environment YAML files are stored under `platform/environments/<category>/<id>.yaml`
- One directory `platform/environments/web-api/juice-shop/` uses directory layout with `compose.yaml`, `manifest.yaml`, `README.md`, and lifecycle scripts because it has Docker runtime artifacts alongside the manifest
- Registry file at `platform/registry.yaml` lists runtime IDs, not environment IDs
- Platform scripts at `platform/scripts/lab-*.sh` discover environments by scanning the `platform/environments/` tree

## Desired convention
- Single curated source of truth for environment registry that maps lab IDs to paths, categories, drivers, and runtime requirements
- Environment IDs are unique across categories
- `platform/environments/web-api/juice-shop/` remains a first-class environment alongside flat YAML files, discovered by the same lab scripts
- Schema validation is applied consistently across all environment definitions
- No personal data, credentials, runtime results, or generated artifacts in the repository
