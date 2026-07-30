#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[reset] Disconnecting Kali..."
docker network disconnect webgoat-lab hermes-kali-mcp 2>/dev/null || true

echo "[reset] Tearing down project with volumes..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[reset] Recreating lab..."
"${COMPOSE[@]}" up -d

echo "[reset] Waiting for healthy..."
timeout 180 bash -c '
  while true; do
    CONTAINER_ID=$(
      docker compose -p webgoat -f '"${COMPOSE_FILE}"' ps -q webgoat 2>/dev/null
    )
    if [ -n "${CONTAINER_ID}" ]; then
      health=$(docker inspect -f "{{.State.Health.Status}}" "${CONTAINER_ID}" 2>/dev/null || echo "none")
      if [ "${health}" = "healthy" ]; then
        exit 0
      fi
    fi
    if [ "${health}" = "unhealthy" ] || [ "${health}" = "none" ]; then
      sleep 5
      continue
    fi
    sleep 5
  done
' || {
  echo "[reset] Timeout or failure waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[reset] Running smoke..."
"${SCRIPT_DIR}/smoke.sh"

echo "[reset] Lab reset complete (Kali remains disconnected)"
