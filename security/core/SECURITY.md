# Security Policy

Runbooks are untrusted input until schema and policy validation completes.

## Prohibited design patterns

- free-form shell commands;
- `shell=True`, `eval`, `exec`, dynamic imports from runbook content;
- implicit target discovery outside an allowlist;
- credentials embedded in Git, logs, evidence or runbooks;
- destructive execution without explicit policy approval;
- marking a runbook stable without positive and negative controls.
