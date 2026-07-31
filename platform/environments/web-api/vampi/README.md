# VAmPI Vulnerable API Lab

## Source and image

- Canonical repository: `erev0s/VAmPI`
- Source commit: `f16052dce83f05847133ec98f01c5193a41de7d8`
- GHCR package: `ghcr.io/pestoura/hermes-vampi`
- Runtime image: `ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229`
- Platform: `linux/amd64`
- BuildKit provenance: `mode=max`
- SBOM: attached to the OCI image index

The image is built by the manually dispatched GitHub-hosted publication workflow from the immutable upstream commit. The runtime Compose never builds from source and never uses a mutable tag.

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

The first start pulls the immutable GHCR digest when it is absent locally. `start.sh` and `reset.sh` do not build images. `destroy.sh` removes only the project container and network, preserves the pulled image, disconnects Kali first and is designed to be idempotent.

## Acceptance

Validate the exact branch SHA, catalog, shell syntax, Compose configuration, immutable GHCR digest, OCI labels, healthy state, loopback-only mapping, temporary Kali DNS/TCP/HTTP, safe scanner execution, reset, destroy, second destroy, final Kali disconnection and unchanged unrelated Docker resources.

Evidence belongs in `.runtime/evidence/vampi/` and must not contain tokens, cookies, payloads, raw HTML or destructive test output.
