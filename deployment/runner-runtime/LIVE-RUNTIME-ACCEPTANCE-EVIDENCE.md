# Live runtime acceptance evidence — Runner HOLD boundary (#354, phase A)

Sanitized canonical record of the **live deployment/runtime acceptance** observed on
2026-08-13/2026-08-14 for the fail-closed Runner HOLD boundary deployed by
[`runtime_deployment.py`](runtime_deployment.py) and served by
[`runner_hold_listener.py`](runner_hold_listener.py).

This document records **observed runtime facts only**. It is evidence, not promotion
authority. Execution promotion remains closed: see
[Execution promotion remains HOLD](#execution-promotion-remains-hold).

## Scope of this acceptance

In scope (observed live):

- OS identity boundary materialization and exactness;
- `/run/hexor/runner-dispatch.sock` ownership and mode;
- systemd socket activation and service supervision;
- an unauthorized local peer connect attempt (negative test);
- an authorized peer connect as the gateway identity, **with no payload**;
- listener HOLD decision and absence of downstream effects;
- absence of a Runner authorization trust store before and after;
- target container state invariance.

Out of scope, deliberately **not** performed: trust binding, execution-policy
enablement, payload transmission, receipt creation, router/adapter/Evidence Plane
invocation, and any pentest effect against WebGoat, Juice Shop or Kali.

## Observed identity boundary

| Identity | UID | GID | Supplementary group | Observation |
|----------|-----|-----|---------------------|-------------|
| `hexor-gateway` | 4100 | 4100 | member of `hexor-dispatch` (4110) | exact |
| `hexor-runner` | 4101 | 4101 | member of `hexor-dispatch` (4110) | exact |
| `hexor-dispatch` | — | 4110 | group | exact |

The observed identities match the declared boundary in
[`runtime-deployment.yaml`](runtime-deployment.yaml) and the canonical example
descriptor `../runtime-promotion/templates/runner-identity-descriptor.example.yaml`.

## Observed dispatch surface

- Socket path: `/run/hexor/runner-dispatch.sock`
- Socket owner `uid:gid` = `4101:4110` (`hexor-runner` : `hexor-dispatch`)
- Socket mode = `0660` (no world access)

This matches the declared `socket:` block of the descriptor.

## Observed systemd state

- `hexor-runner.socket`: **active** and **enabled**.
- `hexor-runner.service`: **active (running)** after socket activation.

Supervision therefore behaved as declared by
[`systemd/hexor-runner.socket`](systemd/hexor-runner.socket) and
[`systemd/hexor-runner.service`](systemd/hexor-runner.service).

## Negative test — unauthorized local peer

An unauthorized local user attempted an `AF_UNIX` `connect()` to the dispatch socket.

- Result: **denied by the kernel at connect time**, `errno=13` (`EACCES`).
- The unauthorized peer never reached the listener; no listener decision was produced
  for it.

This closes the `UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN` observation for the HOLD
boundary at the transport layer. Mode `0660` with group `hexor-dispatch` is the
enforcing control.

## Authorized peer connect — HOLD refusal, no payload

A connection was made as the authorized `hexor-gateway` identity. **No payload was
sent.**

Listener decision as logged:

- decision: `REFUSE_HOLD`
- reason: HOLD boundary; peer observed; no payload; no downstream action
- `peer_uid`: 4100
- `peer_gid`: 4100
- `performed_effects`: `[]`

The listener derived the kernel peer credential through the canonical
`SO_PEERCRED` module and refused, consistent with the HOLD contract in
[`README.md`](README.md). The empty `performed_effects` set is the positive evidence
that no receipt, routing, adapter call, Evidence Plane write or target action occurred.

## Trust store absence

`/etc/hexor/runner/authorization-trust-store.json` was **absent before** the
acceptance and **absent after** it. No trust store was created, installed, read or
synthesized, and no signing key material was generated. Trust binding remains
`enabled: false` in the descriptor.

## Target invariance

The target Docker container state was captured before and after the acceptance and was
**byte-identical**. No target was started, stopped, reconfigured or exercised. No
pentest payload was produced at any point.

## Acceptance result

**Deployment/runtime acceptance: PASS.**

The deployed boundary materialized the declared identities and dispatch surface,
activated under systemd, refused an unauthorized peer at the kernel boundary, and
refused an authorized peer at the HOLD boundary with no effects and no payload.

## Execution promotion remains HOLD

Deployment/runtime acceptance PASS is a **separate axis** from execution promotion.
Promotion semantics are unchanged by this document and remain:

| Field | Value |
|-------|-------|
| listener mode | `HOLD` |
| policy state | `DISABLED` |
| policy default | `deny` |
| `runtime_status` | `NOT_RUN` |
| `execution_authority` | `none` |
| `promotion_allowed` | `false` |

A PASS here does not authorize execution, does not bind trust, and does not promote any
Runner policy. Promotion requires the separate live-promotion evidence chain in
[`../runtime-promotion/LIVE-PROMOTION-EVIDENCE-PACKAGE.md`](../runtime-promotion/LIVE-PROMOTION-EVIDENCE-PACKAGE.md)
plus explicit human approval.

## Sanitization

This record contains only account names/IDs, file and socket metadata, systemd unit
states, an `errno` value and a listener decision. It contains no key material, no
credentials, no trust-store contents, no payloads and no target data.

## Why this is a separate file

`deployment/runner-runtime/README.md` is an **installed artifact**: the deployment
controller copies it to `/opt/hexor/runner-runtime/README.md` and refuses any
non-identical overwrite (`DRIFT_DETECTED`). Editing it in the repository would create
real drift against the live install. This acceptance record is therefore kept as a
separate, non-installed document and referenced from
[`../runtime-promotion/README.md`](../runtime-promotion/README.md).
