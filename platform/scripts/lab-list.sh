#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
find "${PLATFORM_DIR}/environments" -maxdepth 2 -type d -printf '%f\t%p\n' 2>/dev/null | sort || true
if [ "$1" = "--validate" ]; then
  find "${PLATFORM_DIR}/environments" -name '*.yaml' -print 2>/dev/null | sort | while read -r m; do
    python3 - "$m" <<'PY'
import sys
from pathlib import Path
import yaml
p = Path(sys.argv[1])
yaml.safe_load(p.read_text())
print(f"OK {p}")
PY
  done
fi
