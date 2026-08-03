# Security layer agent rules

- `platform/` owns targets, runtimes, networks, lifecycle and deployment.
- `security/` owns runbooks, campaigns, policies, adapters, bindings and calibration state.
- Never place runbooks inside an individual laboratory directory.
- Never duplicate a laboratory manifest inside a pack; reference its canonical `id` through `security/bindings/labs.yaml`.
- Runbook content must not contain free-form `command`, `script`, `shell` or `argv` fields.
- No secrets, credentials, raw evidence, exploit output or sensitive payloads may be committed.
- A new or renamed laboratory must update the binding catalog in the same PR when a security pack depends on it.
- A runbook may remain `experimental` without fixtures; `candidate` or `stable` requires positive and negative controls plus evidence references.
- Generated catalogs are disposable outputs. YAML runbooks and laboratory manifests are canonical.
