# DevSecOps Runner Protocol supervised synthetic-process candidate

## Status

`AS_BUILT` — block 9 of `EPIC-05 — Runner Protocol v2`, delivered through technical
pull request [#121](https://github.com/pestoura/hermes-security-labs/pull/121) and
promoted canonically through lifecycle pull request
[#122](https://github.com/pestoura/hermes-security-labs/pull/122).

The candidate reuses the repository-owned supervised synthetic engine, durable SQLite
idempotency ledger and POSIX process supervisor with a separate fixed DevSecOps worker.
It is not a production DevSecOps runner, does not authorize work and cannot invoke a
scanner, pipeline, repository, network, customer target or request-supplied command.

## Activation

The adapter is:

```text
security/packs/devsecops/src/devsecops_runbooks/supervised_runner_protocol_adapter.py
```

It starts only with:

```text
--conformance-only --synthetic-process-only --durable-ledger /absolute/path/outside/repository.sqlite3
```

Request input cannot select the executable, arguments, working directory, environment or
worker mode. Only synthetic `conformance.process.*` capabilities and the test authorization
reference `authz/conformance/active` are accepted.

## Shared boundary and family isolation

The lifecycle engine is implemented in
`platform/runner-protocol/src/runner_protocol_v2/synthetic_supervised.py`. The DevSecOps
wrapper supplies only its family identifier and fixed worker path. The shared engine imports
no API or DevSecOps package, and the DevSecOps wrapper imports no API implementation.

The fixed execution chain is:

```text
absolute Python interpreter
  -> security/packs/devsecops/src/devsecops_runbooks/synthetic_supervised_worker.py
  -> one allowlisted synthetic mode
```

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

- Technical merge: `16384cdb4223b78da8ed26f8f2ad61038e7e5636`
- Lifecycle validated head: `057ae3041989a6f57f9f4cc5d7f505042d7f9a30`
- Lifecycle merge: `f2be46da70601aafe92a436636d8c09201a1b259`
- PR validate: `31110205273` — success
- PR security/gitleaks: `31110206988` — success
- Post-merge validate: `31110364765` — success
- Post-merge security/gitleaks: `31110364958` — success
- Compatibility: `PASS_SYNTHETIC_PROCESS`
- Runtime declaration: `NO_RUNTIME_CHANGE`

## Explicit limitations

- no production DevSecOps capability mapping;
- no scanner, CI/CD platform, source repository or credential integration;
- no container, namespace, cgroup, seccomp or network sandbox;
- no privilege drop, service account or resource quotas;
- no real authorization lookup, target allowlist or Rules of Engagement enforcement;
- no Evidence Plane integration or chain of custody;
- no automatic reconciliation of abandoned `IN_PROGRESS` effects;
- no production promotion claim;
- AI/MCP remains `NOT_RUN`.

Production execution remains `NOT_RUN`, sandbox status remains `NOT_IMPLEMENTED`, and
promotion remains blocked.

`NO_RUNTIME_CHANGE`
