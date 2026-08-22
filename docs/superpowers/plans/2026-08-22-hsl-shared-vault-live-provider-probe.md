# CHG-HSL-086 Shared Vault Live Provider Probe Implementation Plan

**Goal:** deliver and verify the pre-Secret-Zero HSL network/TLS probe without handling credentials or changing signer authority.

**Architecture:** one disposable non-root probe container joins only `hermes-security-plane`, validates the accepted Vault endpoint with the operator-supplied public CA, emits a sanitized `/32` readiness record, then holds the network namespace stable for later HITL.

## Constraints

- No RoleID, SecretID, wrapping token, Vault token, private key, passphrase or secret custody locator.
- No Vault administration.
- No automatic signer/trust/promotion mutation.
- No automatic fallback to `deployment/vault-lab-l1`.
- No generic shell/executor/scheduler/service surface.
- Runtime mutation is limited to the disposable probe container.

## Task 1 — Contract tests (RED)

Create `deployment/tests/test_shared_vault_live_provider_probe.py` requiring:
- exact consumer endpoint and external network;
- non-root/read-only/cap-drop/no-new-privileges/no-ports/no-Docker-socket compose posture;
- pinned Python base image;
- sanitized closed readiness payload;
- fail-closed endpoint/TLS behavior;
- explicit credential-stage `NOT_RUN` boundary.

Run the focused test and require RED because implementation files do not exist.

## Task 2 — Minimal probe (GREEN)

Create:
- `deployment/shared-vault-hsl/probe/probe.py`;
- `deployment/shared-vault-hsl/probe/Dockerfile`;
- `deployment/shared-vault-hsl/probe/compose.yaml`;
- `deployment/shared-vault-hsl/probe/README.md`.

Use only Python stdlib for the pre-secret probe. Do not add credential APIs. Re-run focused tests to GREEN.

## Task 3 — Hardening

Add deterministic JSON output, strict endpoint parsing, IPv4 `/32` validation, bounded connect timeout, signal-safe hold behavior and negative tests. Run `git diff --check`, focused tests, deployment tests, source-of-truth validation and security/lint gates.

## Task 4 — Change record and exact-SHA

Add `changes/CHG-HSL-086.yaml` with repository validation PASS and runtime initially `NOT_RUN`. Push branch, create PR, require protected workflows GREEN on the exact head SHA, merge and verify post-merge `main` SHA.

## Task 5 — Live pre-secret observation

On HermesJarvas, using merged `main` only:
- confirm Vault healthy;
- launch the disposable probe with the public CA mounted read-only;
- require sanitized `PRE_SECRET_ZERO_NETWORK_READY` output;
- independently inspect `hermes-security-plane` membership and confirm exactly one probe `/32` plus the Vault provider;
- leave the probe running to preserve the network namespace;
- record `SECRETID_ISSUANCE=NOT_RUN` and stop before all credential actions.

## Next gate

The next gate is explicit operator HITL for RoleID/response-wrapped SecretID delivery bound to the observed `/32`, followed by a bounded `VaultSignerAdapter` key observation/signing probe and sanitized provider evidence. That gate is not executed automatically by this plan.
