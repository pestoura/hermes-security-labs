#!/usr/bin/env bash
# Not implemented. There is no generic stop wrapper in this repository.
# Use the real lifecycle interface for the environment:
#   lifecycle.sh unified : platform/environments/<category>/<id>/scripts/lifecycle.sh stop
#   discrete scripts     : platform/environments/web-api/<id>/scripts/stop.sh
#   Phase 2 catalog      : platform/scripts/phase2-compose-lab.sh <id> stop
# Matrix: docs/quickstart.md#7-matriz-de-comandos-de-lifecycle
set -euo pipefail
cat >&2 <<'EOF'
lab-stop.sh is NOT_IMPLEMENTED and changes no runtime state.
Use the per-environment lifecycle interface documented in
docs/quickstart.md (section 7, lifecycle command matrix).
EOF
exit 2
