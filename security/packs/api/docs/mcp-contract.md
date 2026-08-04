# Kali MCP contract

## Current compatibility mode

The Hermes Security Labs manifests expose the generic MCP capability `execute_command`. This project constrains it to one fixed command shape:

```text
python3 /opt/hex0r-api-runner/kali_runner.py execute --payload-b64 <encoded-json>
```

The payload contains only:

- schema version;
- runbook and step IDs;
- allowlisted handler and profile;
- validated arguments;
- request, timeout and response limits;
- evidence selectors and redaction keys.

The runner uses argument arrays and never invokes a shell.

## Future native tools

The preferred evolution is to replace the compatibility tool with native MCP tools such as:

- `api_http_request`
- `api_openapi_discover`
- `api_nuclei_scan`
- `api_sqlmap_scan`
- `api_jwt_test`
- `api_graphql_test`
- `api_race_probe`

The runbook DSL remains unchanged; only the adapter changes.
