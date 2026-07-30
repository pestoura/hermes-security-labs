#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[reset] Removing DVWA project state..."
"${SCRIPT_DIR}/destroy.sh"

echo "[reset] Recreating DVWA project..."
"${SCRIPT_DIR}/start.sh"

"${SCRIPT_DIR}/smoke.sh"

echo "[reset] PASS: clean state recreated and smoke validated"
