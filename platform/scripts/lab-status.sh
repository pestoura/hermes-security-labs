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
ENV_ID="$1"
MANIFEST="${PLATFORM_DIR}/environments/${ENV_ID}/manifest.yaml"
if [ ! -f "${MANIFEST}" ]; then
  echo "Missing manifest: ${MANIFEST}" >&2
  exit 1
fi
python3 - "${MANIFEST}" <<'PY'
import sys
from pathlib import Path
import yaml
p = Path(sys.argv[1])
print(yaml.safe_load(p.read_text())['status'])
PY
