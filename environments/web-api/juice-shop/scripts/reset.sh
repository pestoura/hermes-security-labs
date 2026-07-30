#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
cd /home/estourpm/hermes-labs/platform/environments/web-api/juice-shop
docker compose down --volumes
