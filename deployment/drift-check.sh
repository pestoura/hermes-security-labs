#!/usr/bin/env bash
set -euo pipefail
commit="$(git rev-parse --abbrev-ref --short HEAD 2>/dev/null || echo unknown)"
status="$(git status --porcelain 2>/dev/null | wc -l)"
if [ "$status" -gt 0 ]; then
  echo "DRIFT_DETECTED commit=$commit dirty=$status"
  exit 2
fi
echo "IN_SYNC commit=$commit dirty=0"
