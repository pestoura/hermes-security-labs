#!/usr/bin/env bash
# Apply approved configuration files to a target directory and record state.
# Configuration engineering only: no laboratory, scanner or offensive execution.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${DEPLOY_REPO_DIR:-$(cd "${here}/.." && pwd)}"
target="${DEPLOY_TARGET_DIR:-/home/estourpm/hermes-labs/hermes-security-labs}"
lock="${DEPLOY_LOCK_FILE:-${TMPDIR:-/tmp}/hermes-security-labs-deployment.lock}"

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

exec 9>"$lock"
if ! flock -n 9; then
  echo "another deployment operation holds the lock: ${lock}" >&2
  exit 5
fi

exec python3 "${here}/deployment_tracking.py" deploy --repo "${repo}" "${args[@]}"
