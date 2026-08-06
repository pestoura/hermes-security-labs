# AI/MCP Runner Protocol supervised synthetic-process candidate

## Status

`AS_BUILT` — block 10 of `EPIC-05 — Runner Protocol v2`, delivered through technical
pull request [#124](https://github.com/pestoura/hermes-security-labs/pull/124) and
promoted canonically through lifecycle pull request
[#125](https://github.com/pestoura/hermes-security-labs/pull/125).

The candidate reuses the repository-owned supervised synthetic engine, durable SQLite
idempotency ledger and POSIX process supervisor with a separate fixed AI/MCP worker. It
is not the calibrated AI/MCP runtime and does not authorize or execute handlers, MCP
providers, agents, memory/RAG adapters, campaigns, networks, targets or request-supplied
commands.

## Activation

The adapter is:

```text
security/packs/ai-mcp/src/ai_mcp_runbooks/supervised_runner_protocol_adapter.py
```

It starts only with:

```text
--conformance-only --synthetic-process-only --durable-ledger /absolute/path/outside/repository.sqlite3
```

Request input cannot select the executable, arguments, working directory, environment or
worker mode. Only synthetic `conformance.process.*` capabilities and the test authorization
reference `authz/conformance/active` are accepted.

## Separation from the calibrated AI/MCP runtime

The existing AI/MCP pack contains calibrated runtime, dispatch, execution, provider, campaign
and memory/RAG components. The Runner Protocol candidate imports and invokes none of those
components. It supplies only its family identifier and fixed synthetic worker path to the
shared lifecycle engine.

The fixed execution chain is:

```text
absolute Python interpreter
  -> security/packs/ai-mcp/src/ai_mcp_runbooks/synthetic_supervised_worker.py
  -> one allowlisted synthetic mode
```

No statement in this document upgrades the existing AI/MCP runtime to Runner Protocol
conformance or production readiness.

## Safety and durable semantics

- a durable claim is created before process start;
- completed requests replay after restart without a second process;
- changed effects under the same key are refused;
- uncertain active claims are not automatically reclaimed;
- hard timeout and asynchronous cancellation use bounded process-group cleanup;
- surviving descendants yield `INCONCLUSIVE`, never `PASS`;
- raw stdout and stderr are replaced by hashes, lengths and bounded metadata;
- real capabilities and customer authorization references are refused before claim;
- shutdown waits for tracked synthetic processes to reach terminal cleanup.

## Integrated evidence

- Technical merge: `128371b9c53f4128c3747c32eb03951a21f4cab5`
- Lifecycle validated head: `b716de04a0a722d46f571dccb724d65302c02bd8`
- Lifecycle merge: `40b0e60bbf0fecf0f76da648ab3b3560e02cb41c`
- Technical PR validate: `31112451623` — success
- Technical PR security/gitleaks: `31112451266` — success
- Technical post-merge validate: `31112634614` — success
- Technical post-merge security/gitleaks: `31112635289` — success
- Lifecycle PR validate: `31114183976` — success
- Lifecycle PR security/gitleaks: `31114182111` — success
- Lifecycle post-merge validate: `31114427115` — success
- Lifecycle post-merge security/gitleaks: `31114427152` — success
- Compatibility: `PASS_SYNTHETIC_PROCESS`
- Runtime declaration: `NO_RUNTIME_CHANGE`

## Explicit limitations

- no production AI/MCP Runner Protocol capability mapping;
- no link to the calibrated runtime, handlers, providers, agents or campaigns;
- no MCP provider, model, memory/RAG, Docker, network or target integration;
- no container, namespace, cgroup, seccomp or network sandbox;
- no privilege drop, service account or resource quotas;
- no real authorization lookup, target allowlist or Rules of Engagement enforcement;
- no Evidence Plane integration or chain of custody;
- no automatic reconciliation of abandoned `IN_PROGRESS` effects;
- no production promotion claim.

Production execution remains `NOT_RUN`, sandbox status remains `NOT_IMPLEMENTED`, and
promotion remains blocked.

`NO_RUNTIME_CHANGE`
