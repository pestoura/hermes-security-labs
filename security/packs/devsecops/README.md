# Devsecops Security Runbooks

A versioned library of **120 machine-readable security runbooks** for the `devsecops` domain.

Unlike the bootstrap catalog, every runbook is now stored as an individual YAML file under `runbooks/`.
The YAML files are the canonical source. Any CSV or report is derived from them.

## Coverage

- `repository`: 12
- `secrets`: 16
- `sca`: 16
- `sbom`: 12
- `oci`: 14
- `cicd`: 16
- `supplychain`: 12
- `iac`: 16
- `evidence`: 6

## Definition of complete

Every runbook has a unique ID, target selectors, capabilities, explicit risk limits, three typed steps,
profile-specific evaluation criteria, deterministic evidence requirements encoded in the step arguments,
and a finding output. No runbook contains free-form shell, script, command or argv fields.

## Validation status

The definitions are structurally complete and validated in CI. They remain `experimental` until their
positive and negative controls are calibrated against authorised laboratories. Structural completeness
must not be represented as proof that an external adapter has detected the vulnerability in a live target.

## Commands

```bash
pip install -e '.[dev]'
python tools/validate_pack.py
pytest -q
python tools/export_catalog.py --output dist/catalog.csv
```
