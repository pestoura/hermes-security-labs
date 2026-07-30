#!/usr/bin/env bash
set -euo pipefail
if [ -n "$(git status --porcelain)" ]; then
  echo "dirty_tree" >&2
  exit 2
fi
sha="$(git rev-parse --abbrev-ref --short HEAD)"
compose pass
scripts pass
mcp pass
runtime pass
cat > /home/estourpm/hermes-labs/.deployment.json <<JSON
{
  "repository": "pestoura/hermes-security-labs",
  "branch": "main",
  "commit": "${sha}",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "deployed_by": "hermes-agent",
  "git_dirty": false,
  "validation": {
    "compose": "pass",
    "scripts": "pass",
    "mcp": "pass",
    "runtime": "pass"
  }
}
JSON
