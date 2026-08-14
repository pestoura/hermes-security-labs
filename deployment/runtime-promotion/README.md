# Runtime promotion prerequisites: identities, trust, policy and evidence

This directory carries the **deployment-side** prerequisites that must be satisfied before the
Runner transport, authorization, dispatch and evidence policies can ever be promoted out of
`DISABLED / NOT_RUN`.

Nothing here enables anything. There is no provisioning, no `sudo`, no socket creation, no
service installation and no policy mutation. The preflights are read-only validators over
declared descriptors, policy templates are inert, and the aggregate evidence gate can only
return `HOLD`.

## Why this exists

`platform/runner-transport/README.md` states that `SO_PEERCRED` is only a real boundary when the
gateway has a dedicated operating-system identity. `platform/runner-dispatch/README.md` carries
the corresponding routing and authenticated-principal audit boundary. These requirements must be
machine-checkable before a live promotion can even be considered.

The TB1 authorization chain has a separate deployment boundary. The repository can build a
Hermes-issued receipt, but live promotion still requires a controlled external signer and a
purpose-bound public-key trust store at the Runner. `tb1_authorization_preflight.py` makes that
declaration machine-checkable without loading a private key or installing anything.

`runtime_promotion_evidence_gate.py` then aggregates the **repository evidence only**: accepted
change records, required components, canonical fail-closed policy posture and the live validation
campaign. It never converts evidence into execution authority.

## Contents

| Path | Purpose |
| --- | --- |
| `runner_identity_preflight.py` | Read-only validator for identities, socket ownership/mode and rendered policy templates |
| `templates/runner-transport-policy.enabled.template.yaml` | Exact shape of the promoted transport policy |
| `templates/runner-dispatch-routing-policy.enabled.template.yaml` | Exact shape of the promoted routing policy |
| `templates/runner-identity-descriptor.example.yaml` | Example descriptor, non-operational values |
| `tb1_authorization_preflight.py` | Read-only validator for external signer and public trust-store binding |
| `tb1-authorization-deployment-descriptor.schema.json` | Strict TB1 deployment descriptor schema |
| `templates/tb1-authorization-deployment-descriptor.example.yaml` | Inert TB1 deployment example with public verification material only |
| `TB1-AUTHORIZATION-PREFLIGHT.md` | TB1 deployment preflight contract and limitations |
| `runtime-promotion-evidence-bundle.yaml` | Inert first-live WebGoat L1 repository evidence inventory |
| `runtime_promotion_evidence_gate.py` | Aggregate read-only evidence gate; promotion is always false |

## Identity rules enforced

1. The execution gateway runs under a dedicated non-root UID/GID (`uid != 0`, `gid != 0`).
2. The Runner runs under a **distinct** non-root service identity; gateway and Runner may not
   share a UID, and may not both be a generic shared account.
3. Neither identity may be a login/shell account: `shell` must be a nologin/false path.
4. The Unix socket path is explicitly configured and absolute, under `/run/...` or `/var/run/...`.
5. Socket ownership is exact: owner UID is the Runner identity, group is the dispatch group, and
   the gateway identity is a member of that group.
6. Socket mode is `0660` or tighter, with no world or special permission bits.
7. The parent directory is `0750` or tighter and owned by the Runner identity.
8. The allowlist maps the gateway UID/GID to one principal with purpose `runner-dispatch`.

## Policy template rules enforced

Rendered transport and routing policies are handed to the **canonical product validators**. A
template that fails those validators fails the preflight. The preflight also fixes:

- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- `default: deny`;
- transport mTLS `FUTURE / NOT_CONFIGURED`;
- exact principal/routing binding consistency.

Rendering is not promotion. Live promotion remains a separately authorized decision backed by
runtime evidence.

## TB1 signer / trust-store rules enforced

The TB1 preflight requires:

- Hermes as fixed authorization authority;
- domain `hex0r.tb1.authorization.v1` and purpose `tb1-authorization`;
- an external signer (`KMS`, `HSM`, `VAULT` or `PKCS11`) referenced by a non-secret logical ID;
- `private_key_local: false`;
- signer `key_id`/algorithm matching exactly one active public trust-store key;
- a parseable Ed25519 or P-256 public key matching the declared algorithm;
- a trust-store path below `/etc`, `/run` or `/var/run`;
- no secret/private-shaped fields;
- `runtime_status: NOT_RUN`.

The trust store is checked against the canonical authorization trust-store schema. PASS proves
descriptor consistency only; it does not resolve the provider, install the file or prove key
custody. See [`TB1-AUTHORIZATION-PREFLIGHT.md`](TB1-AUTHORIZATION-PREFLIGHT.md).

## Aggregate evidence-only gate

The canonical first-live bundle is fixed to:

- environment `webgoat`;
- adapter `webgoat-l1`;
- capability `web.discovery.headers`;
- intrusiveness `L1`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- `promotion_mode: EVIDENCE_ONLY`.

The gate verifies that:

1. required chain components exist in the repository;
2. required JDS change records are `ACCEPTED` with accepted targeted/regression evidence;
3. receipt-delivery, resolver, transport, routing and Runner-outcome custody policies all remain
   `DISABLED / deny / NOT_RUN / execution_authority: none`;
4. every required live validation observation not `PASS / RESOLVED` remains an explicit blocker;
5. the canonical campaign recommendation remains `HOLD`.

Even if a future campaign has every required observation resolved, this **evidence-only** gate
still returns `promotion_allowed: false` and the blocker
`HUMAN_PROMOTION_APPROVAL_REQUIRED`. A separate request-bound Human-in-the-Loop promotion record
is mandatory.

Canonical command:

```bash
python3 deployment/runtime-promotion/runtime_promotion_evidence_gate.py --json check
```

A normal current-state result is repository-ready but live-incomplete, with exit `0`,
`promotion_allowed=false`, recommendation `HOLD`, and the unresolved campaign observations listed
as blockers. Exit `2` means the repository bundle itself is invalid or no longer fail-closed.

## Canonical repository state remains fail-closed

The following policies remain deliberately non-operational:

- `platform/runner-authorization/receipt-delivery-policy.yaml`;
- `platform/runner-authorization/resolver-policy.yaml`;
- `platform/runner-transport/transport-policy.yaml`;
- `platform/runner-dispatch/routing-policy.yaml`;
- `platform/evidence-plane/runner-outcome-policy.yaml`.

The aggregate gate checks that posture. It contains no code path that writes those files or
promotes runtime state.

## Other usage

Runner identity/socket declaration:

```bash
python3 deployment/runtime-promotion/runner_identity_preflight.py \
  --descriptor deployment/runtime-promotion/templates/runner-identity-descriptor.example.yaml \
  check
```

TB1 signer/trust-store declaration:

```bash
python3 deployment/runtime-promotion/tb1_authorization_preflight.py \
  --descriptor deployment/runtime-promotion/templates/tb1-authorization-deployment-descriptor.example.yaml \
  --json check
```

Neither command promotes runtime state.

## Still blocking live promotion

Repository preflights and evidence aggregation do not replace privileged runtime evidence.
Remaining blockers include:

1. host evidence that gateway/Runner UIDs/GIDs exist, are dedicated and preserve intended
   container/user-namespace identity;
2. live negative tests from an unauthorized UID/GID against the real Runner socket;
3. live evidence that the declared TB1 signer resolves to the intended protected key;
4. installation/ownership/mode evidence for the Runner authorization trust store;
5. live signed-receipt issuance -> delivery -> verification, including revoked/unauthorized-key
   negative cases;
6. a durable append-only/immutable sink receiving the authenticated-principal dispatch audit
   events with the same Runner correlation IDs;
7. live Runner terminal outcome custody into the Evidence Plane;
8. explicit request-bound Human-in-the-Loop approval for the exact candidate and policy set.

Blocker 2 (live negative test from an unauthorized UID/GID against the real Runner socket) is
now **observed** for the HOLD boundary and recorded in
[`../runner-runtime/LIVE-RUNTIME-ACCEPTANCE-EVIDENCE.md`](../runner-runtime/LIVE-RUNTIME-ACCEPTANCE-EVIDENCE.md),
together with the observed identity/socket exactness and systemd activation. That record is
deployment/runtime acceptance evidence only: it closes no other blocker in this list and changes
no promotion semantics, which remain `runtime_status=NOT_RUN`, `execution_authority=none`,
`promotion_allowed=false`.
