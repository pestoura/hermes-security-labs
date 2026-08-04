# Runbook DSL

The materialised YAML is the execution contract. Every runbook contains:

- identity and lifecycle status;
- OWASP API and CWE mappings;
- applicability selectors;
- explicit risk and request limits;
- declared inputs without embedded secrets;
- one or more allowlisted Kali actions;
- evidence requirements;
- deterministic decision states;
- finding metadata.

## Canonical states

- `secure`
- `vulnerable`
- `inconclusive`
- `skipped`
- `error`

## Source catalog

`runbooks/catalog.csv.gz` stores 150 definitions compactly. Run:

```bash
python tools/export_catalog.py --output dist/catalog.csv
python tools/materialize.py --output dist/runbooks
```

The second command expands each definition into an independent YAML runbook validated by `schemas/runbook.schema.json`.

## Prohibited fields

Runbooks must not contain `command`, `shell`, `script`, `eval`, or free-form tool input. Only `handler`, `profile` and validated arguments are allowed.
