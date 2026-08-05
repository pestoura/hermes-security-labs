#!/usr/bin/env bash
# Report IN_SYNC, DRIFT_DETECTED or UNKNOWN. Never fails open to IN_SYNC.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${DEPLOY_REPO_DIR:-$(cd "${here}/.." && pwd)}"
target="${DEPLOY_TARGET_DIR:-/home/estourpm/hermes-labs/hermes-security-labs}"

args=()
explicit_target=0
for arg in "$@"; do
  case "$arg" in
    --target-dir=*) explicit_target=1 ;;
  esac
  args+=("$arg")
done
if [ "$explicit_target" -eq 0 ]; then
  args+=("--target-dir=${target}")
fi

set +e
python3 "${here}/deployment_tracking.py" drift-check --repo "${repo}" "${args[@]}"
rc=$?
set -e
case "$rc" in
  0|1|2) exit "$rc" ;;
  *) echo '{"status": "UNKNOWN", "reason": "unexpected runner exit"}'; exit 2 ;;
esac
