#!/usr/bin/env bash
# Validate the deployment state file against the target directory.
# Read-only: never repairs anything.
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

exec python3 "${here}/deployment_tracking.py" verify --repo "${repo}" "${args[@]}"
