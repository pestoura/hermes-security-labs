#!/usr/bin/env bash
# Canonical wrapper: delegates to the fail-closed lifecycle dispatcher.
# It provisions nothing by itself and refuses any environment/action pair that
# is not explicitly SUPPORTED by a shipped script.
#   readiness gate : platform/scripts/lab_lifecycle.py support [<env-id>]
#   matrix         : docs/quickstart.md#7-matriz-de-comandos-de-lifecycle
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <env-id> [--dry-run] [--yes]" >&2
  echo "Supported environments: python3 ${SCRIPT_DIR}/lab_lifecycle.py support" >&2
  exit 2
fi
ENV_ID="$1"
shift
exec python3 "${SCRIPT_DIR}/lab_lifecycle.py" run "${ENV_ID}" reset "$@"
