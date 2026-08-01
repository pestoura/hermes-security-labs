#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
LIFECYCLE="$ROOT/platform/scripts/phase2-compose-lab.sh"
SOURCE_FETCHER="$ROOT/platform/runtime/phase2-safe-lab/fetch_source.py"
COMPOSE_GENERATOR="$ROOT/platform/scripts/phase2_compose.py"
RUNTIME="${PHASE2_RUN_RUNTIME:-0}"
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

cleanup_after_failure() {
  local exit_code="$1"
  trap - ERR INT TERM
  if [ "$RUNTIME" = "1" ] && [ -n "$CURRENT_ENV" ]; then
    echo "CLEANUP_AFTER_FAILURE env=$CURRENT_ENV" >&2
    "$LIFECYCLE" "$CURRENT_ENV" destroy >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

trap 'cleanup_after_failure $?' ERR
trap 'cleanup_after_failure 130' INT
trap 'cleanup_after_failure 143' TERM

python3 "$ROOT/platform/scripts/labctl.py" validate
python3 "$ROOT/platform/scripts/labctl.py" plan >/dev/null
python3 "$SOURCE_FETCHER" --self-test
python3 "$COMPOSE_GENERATOR" --self-test
bash -n "$LIFECYCLE"

for env_id in "${ENVIRONMENTS[@]}"; do
  echo "STATIC $env_id"
  "$LIFECYCLE" "$env_id" config >/dev/null
  if [ "$RUNTIME" != "1" ]; then
    continue
  fi

  CURRENT_ENV="$env_id"
  echo "RUNTIME $env_id"
  "$LIFECYCLE" "$env_id" destroy
  "$LIFECYCLE" "$env_id" destroy
  "$LIFECYCLE" "$env_id" start
  "$LIFECYCLE" "$env_id" status
  "$LIFECYCLE" "$env_id" smoke
  "$LIFECYCLE" "$env_id" connect-kali
  "$LIFECYCLE" "$env_id" connect-kali
  "$LIFECYCLE" "$env_id" disconnect-kali
  "$LIFECYCLE" "$env_id" disconnect-kali
  "$LIFECYCLE" "$env_id" stop
  "$LIFECYCLE" "$env_id" start
  "$LIFECYCLE" "$env_id" reset
  "$LIFECYCLE" "$env_id" smoke
  "$LIFECYCLE" "$env_id" destroy
  "$LIFECYCLE" "$env_id" destroy
  CURRENT_ENV=""
done

trap - ERR INT TERM
echo "PHASE2_BATCH_VALIDATION_COMPLETE runtime=$RUNTIME"
