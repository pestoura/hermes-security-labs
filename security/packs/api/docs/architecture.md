# Architecture

## Components

1. **Hermes master/planner** receives an authorised engagement and target profile.
2. **Catalog loader** expands the compact catalog into canonical runbook objects.
3. **Planner** filters by API type, authentication and required capabilities.
4. **Policy engine** validates host scope, environment, intrusiveness and destructive flags.
5. **Executor** renders typed requests and passes them to an adapter.
6. **Kali MCP adapter** creates a call to the existing `execute_command` tool.
7. **Kali runner** accepts only a fixed executable path and an encoded JSON payload, dispatching to allowlisted handlers without `shell=True`.
8. **Evidence and finding layers** will normalise results after laboratory calibration.

## Trust boundaries

```text
LLM / planner
  | untrusted intent
  v
Schema + policy + executor
  | typed request
  v
MCP bridge
  | fixed runner command
  v
Kali runner allowlist
  | argv/network request
  v
Registered isolated target
```

The same scope decision is intentionally repeated at multiple layers. A prompt or planner decision cannot grant scope by itself.

## Initial handlers

- `http`
- `openapi`
- `tls`
- `nuclei`
- `sqlmap`
- `jwt`
- `graphql`
- `websocket`
- `fuzz`
- `race`
- `headers`
- `workflow`

Advanced profiles share handlers but remain separate runbooks because their prerequisites, evidence and decisions differ.
