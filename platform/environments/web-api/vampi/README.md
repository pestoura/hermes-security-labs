# VAmPI Vulnerable API Lab

## Source

- Canonical repository: `erev0s/VAmPI`
- Source commit: `f16052dce83f05847133ec98f01c5193a41de7d8`
- Local image: `hermes/vampi:f16052d`
- Build context is the immutable Git commit above.

## Exposure

- Host: `http://127.0.0.1:${VAMPI_HOST_PORT:-5000}/`
- Kali target: `http://vampi:5000/`
- Swagger UI: `/ui/`
- Network: `vampi-lab`
- Runtime egress: permitted and declared in the manifest.

The service runs with `vulnerable=1`. Do not execute destructive API operations, denial-of-service payloads, external targets or LAN targets during lifecycle acceptance.

## Lifecycle

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/smoke.sh
./scripts/connect-kali.sh
./scripts/disconnect-kali.sh
./scripts/stop.sh
./scripts/reset.sh
./scripts/destroy.sh
```

The first start builds from the pinned upstream commit. `destroy.sh` removes only the project container and network, preserves the built image, disconnects Kali first and is designed to be idempotent.

## Acceptance

Validate the exact branch SHA, catalog, shell syntax, Compose configuration, immutable source reference, healthy state, loopback-only mapping, temporary Kali DNS/TCP/HTTP, safe scanner execution, reset, destroy, second destroy, final Kali disconnection and unchanged unrelated Docker resources.

Evidence belongs in `.runtime/evidence/vampi/` and must not contain tokens, cookies, payloads, raw HTML or destructive test output.
