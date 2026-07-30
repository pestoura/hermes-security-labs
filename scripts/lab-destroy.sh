#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
read -rp "Confirm destroy all local lab environments? [y/N] " answer
if [ "${answer}" != "y" ] && [ "${answer}" != "Y" ]; then
  echo "Aborted."
  exit 2
fi
echo "DRY-RUN destroy"
