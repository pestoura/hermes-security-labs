> **Localização canónica:** `security/core` no monorepo `pestoura/hermes-security-labs`.  
> Importado de `pestoura/security-runbook-core@54be257bad730d9df3c6b855ca3d453f1fb2b63d`; o repositório autónomo é apenas histórico de migração.

# Security Runbook Core

Deterministic engine and canonical contracts for machine-readable security runbooks.

## Responsibilities

- load and validate runbook packs;
- select applicable runbooks from target capabilities;
- enforce scope and execution policies;
- authorize every step at the semantic execution boundary before dispatch;
- create typed action requests;
- normalise evidence and results;
- never accept free-form commands from an LLM.

## Target authorization boundary (fail closed)

`security_runbook_core.target_authorization` is the port through which the
engine asks a canonical authority whether `(target_id, operation_id)` may be
dispatched. `execute_runbook` authorizes **every** step before the adapter is
invoked even once, so a denied target can never reach a handler.

- the caller supplies a canonical `target_id` on the target mapping; a URL,
  hostname or IP address is never accepted as an authority;
- the default authority is `DenyAllAuthorizer`, so an unwired integrator gets a
  deterministic `AUTHORIZER_NOT_CONFIGURED` denial instead of an execution;
- `CallableAuthorizer` adapts the canonical platform resolver
  (`platform/targets/execution_authorization.py`) without making this package
  depend on the platform tree;
- denials raise `AuthorizationRequired` carrying an audit-friendly decision
  (identifiers, boolean, reason code — never a raw locator);
- `lab.lifecycle.stop|reset|destroy|cleanup` are classified `SAFETY` so
  non-offensive teardown stays available.

```python
from security_runbook_core import CallableAuthorizer, execute_runbook

results = execute_runbook(
    runbook,
    {"ref": "lab", "target_id": "juice-shop-web"},
    policy,
    adapter,
    authorizer=CallableAuthorizer(platform_authorize_operation),
)
```

The core is domain-neutral. Domain packs such as `devsecops-security-runbooks`
and `ai-mcp-security-runbooks` provide catalogs, campaigns and adapter profiles.

## Status

`v0.1.0-alpha`: static contracts and deterministic dry-run execution. No target
execution is enabled by default.
