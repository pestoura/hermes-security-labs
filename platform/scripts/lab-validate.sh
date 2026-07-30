#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
find "${PLATFORM_DIR}/environments" -name 'manifest.yaml' -print 2>/dev/null | sort | while read -r m; do
  python3 - "$m" <<'PY'
import sys
from pathlib import Path
import yaml
p = Path(sys.argv[1])
try:
    yaml.safe_load(p.read_text())
    print(f"OK {p}")
except Exception as e:
    print(f"FAIL {p}: {e}")
    sys.exit(1)
PY
done
