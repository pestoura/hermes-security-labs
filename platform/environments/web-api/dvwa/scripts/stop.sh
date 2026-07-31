#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="dvwa"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

"${SCRIPT_DIR}/disconnect-kali.sh"

echo "[stop] Stopping DVWA project containers..."
"${COMPOSE[@]}" stop

for service in dvwa db; do
  id="$("${COMPOSE[@]}" ps -aq "${service}" 2>/dev/null || true)"
  [[ -z "${id}" ]] && continue
  state="$(docker inspect "${id}" --format '{{.State.Status}}')"
  if [[ "${state}" == running || "${state}" == restarting ]]; then
    echo "[stop] ERROR: ${service} remains ${state}" >&2
    exit 1
  fi
done

echo "[stop] Project stopped; volume and networks preserved"
