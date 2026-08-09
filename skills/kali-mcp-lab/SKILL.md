---
name: kali-mcp-lab
description: Lifecycle guidance for Kali MCP lab environments in Hermes Labs.
allowed-tools:
  - terminal
---

# Kali MCP Lab — Hermes Skill

Use this skill for the authorized local Kali MCP lab lifecycle inside `/home/estourpm/hermes-labs/`.

The connectivity authority is `kali-mcp/config/mcp-connectivity.example.yaml` in this repository. This skill must not define a competing transport contract.

## Active rules

- Prefer the canonical zero-listener STDIO transport:
  `docker exec -i hermes-kali-mcp mcp-server`.
- Keep the two container roles distinct: `kali-server-mcp` is the long-running HTTP backend on container loopback; `mcp-server` is the FastMCP STDIO wrapper Hermes executes and it proxies to that local backend.
- Do not publish or register the container-local `127.0.0.1:5000` HTTP listener as the normal Hermes transport. It is a disabled fallback in the canonical connectivity profile.
- Do not use `tools.include: []`: in the current Hermes MCP configuration semantics, an empty include list means no include filter and therefore exposes all discovered tools when the server is enabled.
- Do not enable all discovered Kali tools by default.
- Keep `resources` and `prompts` disabled unless they are explicitly required and separately accepted.
- Use exact literal tool names in an allowlist after discovery and review. Do not use globs for the accepted subset.
- Registration is two-stage and fail-closed:
  1. store the server disabled with a non-matching sentinel include;
  2. test STDIO discovery only;
  3. review the discovered surface and policy mapping;
  4. replace the sentinel with the exact accepted tool names;
  5. enable only after the accepted subset is explicit.
- Never weaken transport isolation or tool filtering merely to make registration succeed.

### Stage 1 reference entry

The live Hermes configuration is runtime state and must not be copied blindly from this example. The bounded first-stage shape is:

```yaml
mcp_servers:
  hermes-kali-mcp:
    command: docker
    args:
      - exec
      - -i
      - hermes-kali-mcp
      - mcp-server
    enabled: false
    connect_timeout: 30
    tools:
      include:
        - __hermes_rta002_no_tool__
      resources: false
      prompts: false
```

The sentinel is intentionally a literal tool name that must not match any real Kali tool. If discovery returns that literal name, fail closed and choose a new reviewed sentinel before continuing.

## Workflow

1. Confirm formal authorization, active lab scope, target allowlist, execution window and stop conditions.
2. Select a registered lab environment and validate its manifest against the platform schema.
3. Validate available resources and the target's membership of the active lab only.
4. Confirm the `hermes-kali-mcp` container is healthy and isolated without changing its network state.
5. Reconcile the live Hermes MCP registration with the canonical STDIO profile.
6. If registration is absent, perform Stage 1 disabled registration and metadata discovery only.
7. Review discovered tool names against the typed operation/tool registry and policy. Keep unneeded or unaccepted tools excluded.
8. Enable only the exact accepted subset required by the authorized scenario.
9. Start/provision the target environment through the canonical lifecycle path.
10. Connect Kali only to the authorized lab target/network boundary required by the scenario.
11. Execute only the typed, authorized and policy-admitted operation; preserve correlated evidence.
12. Disconnect/cleanup, reset the lab and prove known state before closing the run.

## Hard restrictions

Do not allow:

- targets outside a registered and explicitly authorized lab environment;
- LAN, Home Assistant, SPMS, Hermes host or unrelated container targets;
- simultaneous connection to multiple client/lab networks;
- permanent egress or host-port publication for Kali MCP;
- blind MCP registration from historical configuration;
- `tools.include: []` as a deny-all mechanism;
- wildcard tool allowlists for the accepted Kali surface;
- enabling every discovered tool merely because discovery succeeded;
- scans, exploitation, persistence, destructive actions, credential use, lateral movement or data extraction outside the specific authorized scenario and Human-in-the-Loop rules.

## Degraded policy

If a tool or runtime validation is `DEGRADED`:

- record the exact blocker;
- continue only independent lab lifecycle work that remains safe and authorized;
- do not reinterpret `DEGRADED` as functional acceptance;
- do not broaden permissions, transport exposure or tool availability to obtain a pass.
