# CHG-HSL-082 tests-first checkpoint

Date: 2026-08-16
Issue: #426
PR: #427
Scope: repository deployment package for the isolated Hermes LAB_L1 Vault capability

## Authoritative non-live state

This checkpoint records repository evidence only. It does not assert that a Vault service, Shamir shares, root bootstrap credential, AppRole SecretID, Transit key, provider attestation or trust binding exists on the Hermes runtime.

The canonical state remains:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
trust = UNBOUND
promotion_allowed=false
runtime_status=NOT_RUN
execution_authority=NONE
campaign=BLOCKED / HOLD
```

## Tests-first RED

Exact tests-first head:

`16142317f8fdea3c15e3e0414c74fcdf0815a5c1`

Validate run:

`31959789885`

The new `deployment/tests/test_vault_lab_l1_capability.py` contract failed before implementation exactly because the CHG-HSL-082 deployment artefacts were absent:

```text
deployment/tests = 9 failed, 561 passed
```

The existing suites remained healthy at the RED checkpoint, including security, Release governance and Private VAmPI source-repo access deny. No production Vault deployment code was written before this RED was observed.

## First implementation feedback

Initial implementation head:

`7c590004208578139720b265528eb856ab0dfef3`

Validate run:

`31960297531`

The full suite found one pre-existing transversal hardening conflict:

```text
platform/tests = 1 failed, 2366 passed, 7 skipped
failed = test_only_allowlisted_host_bind_mounts_exist
cause = deployment/vault-lab-l1/compose.yaml declared new host bind mounts
```

The failure was not bypassed and the repository-wide allowlist was not expanded.

Root cause: the first Compose draft used direct host bind mounts for Vault configuration, policies and TLS material, while the canonical container-hardening baseline forbids non-allowlisted service bind mounts.

Correction:

- Raft state remains the only service `volume`, using a named Docker volume;
- Vault HCL and policy files are delivered through Compose `configs`;
- TLS CA/certificate/private-key material is granted through Compose `secrets` rather than general service volumes;
- `SKIP_SETCAP=1` is paired with `disable_mlock=true` and `cap_drop: [ALL]`, so the Vault container does not require an added Linux capability;
- the hardening baseline itself was not weakened.

## First full GREEN candidate

Exact head:

`fe5f79613d62068ec330325e50fcc3ffe79545d2`

Canonical runs:

```text
validate                         31960587747  PASS
security                         31960587758  PASS
Release governance               31960587752  PASS
Private VAmPI source-repo deny   31960587756  PASS
Exact-SHA job                    95198213156  PASS
```

Observed validate counts:

```text
YAML files       = 660 parsed
Docs             = 1123 passed
Platform         = 2367 passed, 7 skipped
Roadmap          = 146 passed
Deployment       = 570 passed
Shell syntax     = PASS
Compose/runtime  = PASS
Exact-SHA        = PASS
```

## Result

The implementation reached repository GREEN without adding a bind-mount exception, without enabling dev mode, without relaxing TLS, without adding Vault administration to the signer policy, and without changing signer selection/trust/promotion authority.

A final documentation/governance reconciliation follows this checkpoint and must itself pass exact-head CI before merge. Runtime remains `NOT_RUN` until a separate execution on the Hermes host captures sanitized real capability evidence.