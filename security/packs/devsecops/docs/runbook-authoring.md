# Runbook authoring rules

- The canonical unit is one YAML file per runbook under `runbooks/<category>/`.
- IDs and `(category, primary profile)` pairs must be unique.
- Every definition contains a baseline step, a typed control step and a typed evidence/evaluation step.
- `command`, `script`, `shell` and `argv` are forbidden anywhere in a definition.
- Every result must distinguish `vulnerable`, `secure` and `inconclusive` using explicit signals.
- All definitions remain `experimental` until positive and negative controls pass in an authorised lab.
- The expected pack size is 120; reducing it requires an explicit deprecation migration.
