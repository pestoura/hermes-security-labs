# Runner transport identity

This directory defines authentication of the **transport peer** between the execution gateway and a Runner. It is deliberately separate from Runner Protocol v2 and from TB1 operation authorization.

## Authority separation

- Hermes remains the only pentest execution-authorization authority.
- A valid `runner.step.request` is not sufficient to prove who delivered it.
- Transport identity is derived out-of-band from the accepted channel; it is never accepted from Runner JSON fields.
- Transport authentication cannot create, extend or replace a TB1 authorization receipt.
- Adapter dispatch is not implemented in this lane.

## MVP candidate: Unix peer credentials

For a same-host gateway/Runner deployment, the candidate uses Linux `SO_PEERCRED` on an accepted `AF_UNIX` socket. The kernel supplies the peer PID, UID and GID. Policy then maps an **exact UID/GID pair** to a named principal with purpose `runner-dispatch`.

The implementation refuses:

- non-Unix sockets;
- unavailable or invalid kernel peer credentials;
- disabled policy;
- unknown UID/GID pairs;
- duplicate/ambiguous credential mappings;
- wildcard or string UID/GID values;
- non-absolute socket paths when enabled;
- any claim that transport identity itself is execution authority.

The committed `transport-policy.yaml` is intentionally:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `socket_path: NOT_CONFIGURED`;
- `allowed_peers: []`.

Repository acceptance therefore cannot enable a live Runner channel.

## Deployment requirement before promotion

`SO_PEERCRED` is only useful as a security boundary when the gateway has a dedicated operating-system identity. If gateway, Runner and unrelated processes share the same UID/GID — especially UID 0 — the mapping does not provide sufficient process separation.

Before runtime promotion, the deployment must therefore prove at least:

1. a dedicated non-root UID/GID for the execution gateway;
2. a distinct Runner service identity;
3. an explicitly configured Unix socket path;
4. restrictive socket owner/group/mode;
5. exact allowlist mapping from the gateway UID/GID to one principal;
6. evidence that container/user-namespace mapping preserves the intended host identity;
7. live negative tests from an unauthorized UID/GID;
8. audit logging of the authenticated principal alongside Runner correlation IDs.

Until those checks pass, this remains `CANDIDATE / NOT_RUN`.

## Distributed runners

mTLS (mutual Transport Layer Security) with purpose-bound client certificates is the planned transport for distributed runners. It remains `FUTURE` and `NOT_CONFIGURED` in this lane. The Unix candidate must not silently fall back to TCP or unauthenticated network transport.

## Non-goals

This block does not implement:

- Runner request dispatch;
- adapter routing;
- TB1 receipt issuance or resolution;
- target selection;
- Evidence Plane persistence;
- remote/mTLS transport;
- container sandboxing;
- runtime enablement.
