# PyGoat Lab

## Source and build

- Canonical repository: `adeyosemanputra/pygoat`
- Source commit: `19d17cc8874861142b330636d068bbde54e86b85`
- Local image: `hermes/pygoat:19d17cc`

The upstream source is immutable. A project-contained inline Dockerfile uses Python 3.11 on Debian Bookworm because the upstream Dockerfile pins obsolete Buster package versions. Application source is not modified.

## Targets

- Host: `http://127.0.0.1:${PYGOAT_HOST_PORT:-8000}/`
- Kali: `http://pygoat:8000/`

Only loopback is published. Runtime egress is declared as permitted.

## Lifecycle and evidence

Use the eight executable lifecycle scripts under `scripts/`. First start builds the pinned source. Reset destroys container state and recreates it from the built image. Destroy disconnects Kali, removes project resources, preserves the image and supports a second execution.

Acceptance is limited to connectivity and bounded safe scanning. Do not perform exploitation, brute force, destructive actions, denial of service, external targets or LAN targets.

Store sanitised evidence in `.runtime/evidence/pygoat/`.
