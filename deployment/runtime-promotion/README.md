# Runtime promotion prerequisites: identities, socket and policy templates

This directory carries the **deployment-side** prerequisites that must be satisfied before the
Runner transport and dispatch policies can ever be promoted out of `DISABLED / NOT_RUN`.

Nothing here enables anything. There is no provisioning, no `sudo`, no socket creation, no
service installation and no policy mutation. The preflights are pure, read-only validators over
declared descriptors, and the templates are inert files that a future, separately authorized
deployment step would render.

## Why this exists

`platform/runner-transport/README.md` states that `SO_PEERCRED` is only a real boundary when the
gateway has a dedicated operating-system identity, and lists eight promotion requirements.
`platform/runner-dispatch/README.md` repeats the same blocker for dispatch. Those requirements
were prose only; this block makes requirements 1-5 machine-checkable and pins the exact shape of
the enabled policies.

The TB1 authorization chain has a separate deployment boundary. The repository can now build a
Hermes-issued receipt, but live promotion still requires a controlled external signer and a
purpose-bound public-key trust store at the Runner. `tb1_authorization_preflight.py` makes that
declaration machine-checkable without loading a private key or installing anything.

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

## Identity rules enforced

1. The execution gateway runs under a dedicated non-root UID/GID (`uid != 0`, `gid != 0`).
2. The Runner runs under a **distinct** non-root service identity; gateway and Runner may not
   share a UID, and may not both be a generic shared account.
3. Neither identity may be a login/shell account: `shell` must be a nologin/false path.
4. The Unix socket path is explicitly configured and absolute, under a runtime directory
   (`/run/...` or `/var/run/...`), and is not world-writable by path placement.
5. Socket ownership is exact: owner UID is the Runner identity (it binds the socket), group is a
   shared dispatch group, and the gateway identity is a member of that group.
6. Socket mode is restrictive: `0660` or tighter, never any world bit, never the setuid/setgid/
   sticky bits.
7. The parent directory mode is `0750` or tighter and owned by the Runner identity.
8. The declared allowlist maps exactly the gateway UID/GID to exactly one principal with purpose
   `runner-dispatch`.

## Policy template rules enforced

The rendered transport and routing policies are handed to the **canonical validators**
(`platform/runner-transport/unix_peer_identity.validate_policy` and
`platform/runner-dispatch/router.validate_policy`). A template that would not pass the product's
own validator fails the preflight. The preflight additionally asserts that:

- rendered `runtime_status` remains `NOT_RUN`;
- rendered `execution_authority` remains `none`;
- rendered `default` remains `deny`;
- the transport `mtls` mode remains `FUTURE / NOT_CONFIGURED`;
- routing bindings reference exactly the principal declared in the transport allowlist.

Because `runtime_status` stays `NOT_RUN` even in the rendered template, rendering a template is
still not a live promotion. Live promotion remains a separate, explicitly authorized decision
backed by acceptance evidence.

## TB1 signer / trust-store rules enforced

The TB1 preflight requires a strict declaration with:

- Hermes as the fixed authorization authority;
- domain `hex0r.tb1.authorization.v1` and purpose `tb1-authorization`;
- an external signer kind (`KMS`, `HSM`, `VAULT` or `PKCS11`) referenced only by a non-secret
  logical identifier;
- `private_key_local: false`;
- a signer `key_id`/algorithm that matches exactly one active key in the public trust store;
- a cryptographically parseable Ed25519 or P-256 public key matching the declared algorithm;
- a restricted trust-store install path below `/etc`, `/run` or `/var/run`;
- no secret/private-shaped fields anywhere in the declaration;
- `runtime_status: NOT_RUN`.

The trust-store document is validated against the canonical
`platform/authorization-contract/authorization-trust-store.schema.json`. PASS proves descriptor
consistency only; it does not resolve the provider, install the file or prove live key custody.
See [`TB1-AUTHORIZATION-PREFLIGHT.md`](TB1-AUTHORIZATION-PREFLIGHT.md).

## Canonical repository state is unchanged

`platform/runner-transport/transport-policy.yaml` and
`platform/runner-dispatch/routing-policy.yaml` remain `DISABLED / deny / NOT_RUN /
execution_authority: none` with no configured socket and no bindings. The TB1 receipt-delivery
policy also remains disabled/not-run. This block does not modify them.

## Usage

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

Exit `0` means the descriptor satisfies the repository prerequisites; exit `2` means fail-closed.
`--json` emits a machine-readable report. Neither command promotes runtime state.

## Still blocking live promotion

The preflights validate *declarations*. They deliberately do not provision or inspect privileged
live state. Remaining blockers include:

1. host evidence that the declared UIDs/GIDs actually exist and are dedicated;
2. evidence that container/user-namespace mapping preserves the intended host identity;
3. live negative tests from an unauthorized UID/GID against a real socket;
4. audit logging of the authenticated principal alongside Runner correlation IDs;
5. live evidence that the declared TB1 signing provider resolves to the intended protected key;
6. installation/ownership/mode evidence for the Runner authorization trust store;
7. a live signed-receipt issuance -> delivery -> verification acceptance, including revoked or
   unauthorized-key negative cases;
8. an explicit, authorized promotion decision moving canonical policies off `NOT_RUN`.
