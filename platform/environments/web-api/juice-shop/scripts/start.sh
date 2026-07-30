#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="juice-shop"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[start] Validating compose..."
"${COMPOSE[@]}" config --quiet || {
  echo "[start] Compose validation failed"
  exit 1
}

echo "[start] Pulling image..."
"${COMPOSE[@]}" pull --quiet || true

echo "[start] Starting juice-shop..."
"${COMPOSE[@]}" up -d

echo "[start] Waiting for healthy (timeout 120s)..."
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
  echo "[start] Timeout or failure waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[start] Juice Shop is healthy"
"${COMPOSE[@]}" ps
