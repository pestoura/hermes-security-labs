source "$(dirname "$0")/env.sh"
#!/usr/bin/env bash
set -euo pipefail
cd /home/estourpm/hermes-labs/kali-mcp
printf 'This script intentionally does not remove data or volumes.\n'
if [ "${1:-}" = "--dry-run" ]; then
  echo 'DRY-RUN destroy requested.'
  docker compose -p hermes-kali-mcp ps || true
  exit 0
fi
echo 'Destruction is not executed automatically without explicit maintenance confirmation.'
