#!/usr/bin/env bash
# Not implemented. There is no generic reset wrapper in this repository.
# Use the real lifecycle interface for the environment:
#   lifecycle.sh unified : platform/environments/<category>/<id>/scripts/lifecycle.sh reset
#   discrete scripts     : platform/environments/web-api/<id>/scripts/reset.sh
#   Phase 2 catalog      : platform/scripts/phase2-compose-lab.sh <id> reset
# Matrix: docs/quickstart.md#7-matriz-de-comandos-de-lifecycle
set -euo pipefail
cat >&2 <<'EOF'
lab-reset.sh is NOT_IMPLEMENTED and changes no runtime state.
Use the per-environment lifecycle interface documented in
docs/quickstart.md (section 7, lifecycle command matrix).
EOF
exit 2
