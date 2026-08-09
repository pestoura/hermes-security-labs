#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=kali-mcp/scripts/env.sh
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd /home/estourpm/hermes-labs/kali-mcp
printf 'This script intentionally does not remove data or volumes.\n'
if [ "${1:-}" = "--dry-run" ]; then
  echo 'DRY-RUN destroy requested.'
  docker compose -p hermes-kali-mcp ps || true
  exit 0
fi
echo 'Destruction is not executed automatically without explicit maintenance confirmation.'
