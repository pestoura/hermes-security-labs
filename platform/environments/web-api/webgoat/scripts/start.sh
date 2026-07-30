#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

WEBGOAT_HOST_PORT="${WEBGOAT_HOST_PORT:-8080}"
WEBWOLF_HOST_PORT="${WEBWOLF_HOST_PORT:-9090}"

echo "[start] Validating compose..."
"${COMPOSE[@]}" config --quiet || {
  echo "[start] Compose validation failed"
  exit 1
}

echo "[start] Checking image digest..."
if ! docker image inspect webgoat/webgoat@sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7 >/dev/null 2>&1; then
  echo "[start] Image not present locally, pulling..."
  "${COMPOSE[@]}" pull || {
    echo "[start] Image pull failed"
    exit 1
  }
fi

echo "[start] Validating port availability: ${WEBGOAT_HOST_PORT}, ${WEBWOLF_HOST_PORT}..."
for port in "${WEBGOAT_HOST_PORT}" "${WEBWOLF_HOST_PORT}"; do
  if ss -ltn "sport = :${port}" | grep -q "LISTEN"; then
    echo "[start] ERROR: Port ${port} is already in use on localhost"
    exit 1
  fi
done

echo "[start] Starting webgoat..."
"${COMPOSE[@]}" up -d

echo "[start] Waiting for healthy (timeout 180s)..."
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
      if [ "${health}" = "unhealthy" ] || [ "${health}" = "none" ]; then
        sleep 5
        continue
      fi
    fi
    sleep 5
  done
' || {
  echo "[start] Timeout or failure waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[start] WebGoat is healthy"
"${COMPOSE[@]}" ps
