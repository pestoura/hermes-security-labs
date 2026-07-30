#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
cd /home/estourpm/hermes-labs/platform/environments/web-api/juice-shop
read -rp 'Confirm destroy juice-shop lab? [y/N] ' answer
if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
  echo "Aborted."
  exit 2
fi
docker compose down --volumes --remove-orphans
