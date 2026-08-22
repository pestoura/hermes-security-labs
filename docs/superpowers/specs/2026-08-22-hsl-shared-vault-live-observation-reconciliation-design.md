# CHG-HSL-087 — Shared Vault live observation reconciliation

## Intent

Reconcile repository source-of-truth after the accepted CHG-HSL-086 probe was executed from merged `main` on HermesJarvas.

The runtime observation proved only the pre-Secret-Zero shared-Vault network/TLS boundary. It did not authenticate the HSL signer, bind trust, enable policy, select a supplier, or authorize a Runner effect.

## Known live facts

- shared Hermes Vault is initialized, unsealed and healthy;
- HSL probe joined only `hermes-security-plane`;
- exact endpoint `https://hermes-vault:8200` resolved and completed hostname-verified TLS;
- TLS version observed: `TLSv1.3`;
- the probe obtained a single IPv4 `/32` consumer identity;
- the probe remains credential-free and preserves `credential_stage=NOT_RUN`;
- `promotion_allowed=false` and `execution_authority=NONE` remain invariant.

## Required repository reconciliation

- update the walking-skeleton status from the stale 2026-08-15 view;
- record CHG-HSL-085/086 and the accepted shared-Vault path;
- mark the isolated CHG-HSL-082 runtime path as superseded/historical;
- update the governed campaign evidence text without resolving signer/trust blockers;
- add CHG-HSL-087 as the live-observation reconciliation record.
## Locked boundaries

This change must not:

- read, create, unwrap, log or persist RoleID, SecretID, wrapping token or Vault token;
- change `signer-human-decision.yaml` from `NO_DECISION`;
- change `supplier_selection` from `NO_SELECTION`;
- install or bind a trust-store generation;
- enable receipt-delivery, resolver, audit-custody or Runner policies;
- change the campaign from `BLOCKED / HOLD`;
- claim signer/provider attestation or R1–R8 completion;
- execute any target-interacting action.

The observed consumer `/32` is runtime topology metadata, not an authorization grant. It may be recorded only as sanitized evidence.

## Acceptance

Repository tests must prove both sides of the state transition:

1. the shared Vault pre-Secret-Zero live observation is represented as PASS/observed evidence;
2. all downstream authority gates remain explicitly incomplete and fail closed.

No automatic transition beyond this reconciliation is permitted.