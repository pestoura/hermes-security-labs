# CHG-HSL-088 — Authenticated receipt-delivery runtime

## Decision

Add a dedicated AF_UNIX receipt-delivery boundary at `/run/hexor/runner-authz.sock`.
The boundary is separate from `/run/hexor/runner-dispatch.sock` and therefore cannot
become an execution-dispatch bypass.

The server runs as `hexor-runner` (uid 4101). The only accepted control-plane peer
is the existing `hexor-gateway` uid 4100. Peer identity is derived from Linux
`SO_PEERCRED`; `hexor-dispatch` group membership provides DAC access only and is
never treated as authentication.

## Runtime model

Use systemd socket activation and the existing `/run/hexor` runtime directory.
The package depends on the already-provisioned canonical identities and does not
create, delete or mutate users/groups.

The listener has two fail-closed states:

1. committed/runtime default: authenticated HOLD; validate the peer, refuse safely,
   and do not read a receipt while receipt-delivery policy is disabled;
2. enabled composition: after a separately governed policy/trust transition, read
   one bounded JSON envelope and delegate it to canonical `TrustedReceiptDelivery`.

No state may enable Runner dispatch, adapters, Kali, WebGoat or target access.
## Framing and safety

When enabled, accept one UTF-8 JSON object per connection, newline terminated,
with a maximum of 65536 bytes and a 2-second read timeout. Reject invalid UTF-8,
invalid JSON, non-object roots, over-limit input and extra trailing data.

Never echo a receipt, signature, credential or raw backend exception. Safe responses
contain only stable status/code fields plus sanitized authorization reference,
sequence and duplicate state after successful canonical delivery.

Restart remains fail-closed: no delivery sequence or resolver cache persistence is
introduced by this change.

## Deployment and governance

Create a dedicated deployment package and systemd socket/service. Installation is
idempotent, drift-sensitive and must never overwrite a differing installed file.
The package must not bind a trust store or enable resolver/delivery policy.

Repository/runtime defaults remain `DISABLED / deny / NOT_RUN`,
`execution_authority=none`, `promotion_allowed=false`, campaign `BLOCKED/HOLD`.

## Acceptance

- TDD proves artifacts/capability absent before implementation.
- Authorized uid 4100 is accepted as the canonical gateway principal; other peers
  are refused before payload read.
- Disabled delivery policy proves authenticated HOLD with zero receipt read.
- Enabled synthetic composition proves bounded framing -> canonical delivery.
- systemd and deployment contracts preserve non-root hardening and no target effect.
- full regression, validation, lint, secret scan and exact-SHA CI are GREEN.