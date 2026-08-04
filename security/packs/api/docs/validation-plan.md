# Validation plan

## Gate 0 — static

- load exactly 150 unique runbooks;
- validate every expanded runbook against JSON Schema;
- reject command and shell fields;
- validate campaigns and policy decisions;
- render deterministic MCP envelopes;
- run unit tests and linting.

## Gate 1 — runner installation

- install or mount `runner/kali_runner.py` at `/opt/hex0r-api-runner/kali_runner.py`;
- set `HEX0R_ALLOWED_HOSTS` from the active lab manifest;
- verify all required tools and versions;
- validate negative scope tests.

## Gate 2 — reference laboratories

- CRAPI: authentication, BOLA, BFLA and business logic;
- VAmPI and DVAPI: baseline API coverage;
- GraphQL vulnerable lab: introspection, batching, alias and complexity;
- Juice Shop/WebGoat/NodeGoat/PyGoat: supporting Web/API cases.

Each runbook requires:

1. a vulnerable positive control;
2. a secure or remediated negative control;
3. sanitised evidence;
4. stable decision logic;
5. bounded request count;
6. documented false-positive conditions.

## Gate 3 — promotion

Only after both controls pass may `metadata.status` become `stable`. Validation progress should be split into issues by category and laboratory rather than bulk-promoting the catalog.
