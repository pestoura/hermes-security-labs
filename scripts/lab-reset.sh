#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ $# -ne 1 ]; then
  echo "Usage: $0 <env-id>" >&2
  exit 2
fi
echo "DRY-RUN reset $1"
