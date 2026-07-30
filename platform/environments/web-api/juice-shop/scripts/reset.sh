#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="juice-shop"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[reset] Disconnecting Kali MCP if connected..."
docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp 2>/dev/null || true

echo "[reset] Removing containers and volumes..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[reset] Recreating lab..."
"${COMPOSE[@]}" pull --quiet || true
"${COMPOSE[@]}" up -d

echo "[reset] Waiting for healthy..."
timeout 120 bash -c '
  while true; do
    health=$(docker inspect -f "{{.State.Health.Status}}" juice-shop 2>/dev/null || echo "none")
    if [ "$health" = "healthy" ]; then
      exit 0
    fi
    if [ "$health" = "unhealthy" ] || [ "$health" = "none" ]; then
      sleep 2
      continue
    fi
    sleep 2
  done
' || {
  echo "[reset] Timeout waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[reset] Running smoke test..."
"${SCRIPT_DIR}/smoke.sh" || exit 1

echo "[reset] Lab reset complete and healthy"
"${COMPOSE[@]}" ps
