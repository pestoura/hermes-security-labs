#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
LIFECYCLE="$ROOT/platform/scripts/phase2-compose-lab.sh"
LIFECYCLE_SELF_TEST="$ROOT/platform/scripts/phase2-compose-lifecycle-self-test.sh"
SOURCE_FETCHER="$ROOT/platform/runtime/phase2-safe-lab/fetch_source.py"
COMPOSE_GENERATOR="$ROOT/platform/scripts/phase2_compose.py"
RUNTIME="${PHASE2_RUN_RUNTIME:-0}"
CONTINUE_ON_FAILURE="${PHASE2_CONTINUE_ON_FAILURE:-0}"
CURRENT_ENV=""

ENVIRONMENTS=(
  cicd-goat
  damn-vulnerable-sca
  terragoat
  cdkgoat
  cfngoat
  bicepgoat
  promptme
  vulnerable-mcp-servers
  llmforge
  damn-vulnerable-llm-agent
  prompt-injection-lab
  tool-poisoning-lab
  rag-poisoning-lab
)

cleanup_environment() {
  local env_id="$1"
  echo "CLEANUP_AFTER_FAILURE env=$env_id" >&2
  "$LIFECYCLE" "$env_id" destroy >/dev/null 2>&1 || true
}

cleanup_current_and_exit() {
  local exit_code="$1"
  trap - INT TERM
  if [ "$RUNTIME" = "1" ] && [ -n "$CURRENT_ENV" ]; then
    cleanup_environment "$CURRENT_ENV"
  fi
  exit "$exit_code"
}

run_environment() {
  local env_id="$1" action rc
  local actions=(
    destroy destroy start status smoke
    connect-kali connect-kali disconnect-kali disconnect-kali
    stop start reset smoke destroy destroy
  )
  for action in "${actions[@]}"; do
    "$LIFECYCLE" "$env_id" "$action" || {
      rc=$?
      echo "PHASE2_ENVIRONMENT_STEP_FAILED env=$env_id action=$action exit=$rc" >&2
      return "$rc"
    }
  done
}

trap 'cleanup_current_and_exit 130' INT
trap 'cleanup_current_and_exit 143' TERM

python3 "$ROOT/platform/scripts/labctl.py" validate
python3 "$ROOT/platform/scripts/labctl.py" plan >/dev/null
python3 "$SOURCE_FETCHER" --self-test
python3 "$COMPOSE_GENERATOR" --self-test
bash -n "$LIFECYCLE"
bash -n "$LIFECYCLE_SELF_TEST"
bash "$LIFECYCLE_SELF_TEST"

for env_id in "${ENVIRONMENTS[@]}"; do
  echo "STATIC $env_id"
  "$LIFECYCLE" "$env_id" config >/dev/null
done

if [ "$RUNTIME" != "1" ]; then
  trap - INT TERM
  echo "PHASE2_BATCH_VALIDATION_COMPLETE runtime=0"
  exit 0
fi

failures=()
for env_id in "${ENVIRONMENTS[@]}"; do
  CURRENT_ENV="$env_id"
  echo "RUNTIME $env_id"
  if run_environment "$env_id"; then
    echo "PHASE2_ENVIRONMENT_PASS env=$env_id"
    CURRENT_ENV=""
  else
    rc=$?
    cleanup_environment "$env_id"
    CURRENT_ENV=""
    failures+=("$env_id:$rc")
    echo "PHASE2_ENVIRONMENT_BLOCKED env=$env_id exit=$rc" >&2
    if [ "$CONTINUE_ON_FAILURE" != "1" ]; then
      exit "$rc"
    fi
  fi
done

trap - INT TERM
if [ "${#failures[@]}" -gt 0 ]; then
  printf 'PHASE2_BATCH_FAILURE %s\n' "${failures[@]}" >&2
  echo "PHASE2_BATCH_LOCAL_ACCEPTANCE_BLOCKED count=${#failures[@]}" >&2
  exit 1
fi

echo "PHASE2_BATCH_VALIDATION_COMPLETE runtime=1"
echo "PHASE2_BATCH_LOCAL_ACCEPTANCE_PROVED"
