---
name: kali-mcp-lab
description: Lifecycle guidance for Kali MCP lab environments in Hermes Labs.
allowed-tools:
  - terminal
---

# Kali MCP Lab — Hermes Skill

Use this skill for the local Kali MCP lab lifecycle inside `/home/estourpm/hermes-labs/`.

## Active rules

- Do not use `tools.include`.
- Keep all 12 Kali MCP tools available.
- Use exclusively `@url:\`http://127.0.0.1:5000\``.
- Do not use bare `@url:` or `@url:\`https://127.0.0.1:5000\``.

## Workflow

1. Select a registered lab environment.
2. Validate the manifest against the platform schema.
3. Validate available resources.
4. Confirm the target belongs to the active lab only.
5. Start the environment.
6. Connect Kali only to that lab network.
7. Execute tools and store evidence under `/data/results`.
8. Disconnect Kali from the lab network.
9. Reset or destroy the environment.
10. Produce a report.

## Hard restrictions

Do not allow:
- targets outside a registered lab environment
- LAN, Home Assistant, SPMS, or Hermes host targets
- simultaneous connection to multiple networks
- permanent egress
- real cloud resources outside sandboxed environments

## Degraded policy

If a tool validates as `DEGRADED`:
- record the exact blocker,
- continue the lab lifecycle,
- do not treat it as a global stop.
