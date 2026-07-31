# Damn Vulnerable GraphQL Application Lab

## Source

- Canonical repository: `dolevf/Damn-Vulnerable-GraphQL-Application`
- Source commit: `a961308c02d1fb462b192681c336b0739e432da7`
- Local image: `hermes/dvga:a961308`

The image is built from the immutable upstream commit during first start.

## Targets

- Host: `http://127.0.0.1:${GRAPHQL_LAB_HOST_PORT:-5013}/`
- Kali: `http://graphql-vulnerable-lab:5013/`

Only loopback is published. Runtime egress remains possible through the application bridge and is declared in the manifest.

## Lifecycle

Use the eight scripts under `scripts/` for start, status, smoke, temporary Kali connection, stop, reset and deterministic destroy. The destroy operation disconnects Kali first and is idempotent.

## Acceptance limits

Lifecycle acceptance is non-exploitative. Do not run denial-of-service queries, deep recursion, command execution, SSRF, SQL injection, arbitrary file writes or external targets. Safe evidence is limited to DNS, TCP connect, basic HTTP, Nmap TCP-connect, Nikto and bounded Gobuster.

Store only sanitised evidence under `.runtime/evidence/graphql-vulnerable-lab/`.
