#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
# Application service: owns the pinned image digest and the workload health gate.
SERVICE_NAME="webgoat"
# Publication service: the ONLY service that declares host port mappings, so the
# lab is not usable (and smoke cannot pass) until it is healthy too.
PUBLISH_SERVICE_NAME="webgoat-proxy"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

# shellcheck source=lib-health.sh
source "${SCRIPT_DIR}/lib-health.sh"

HEALTH_TIMEOUT_SECONDS="${WEBGOAT_HEALTH_TIMEOUT_SECONDS:-300}"

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

echo "[start] Waiting for healthy application and publication services (timeout ${HEALTH_TIMEOUT_SECONDS}s)..."
wait_for_services_healthy "start" "${HEALTH_TIMEOUT_SECONDS}" "${SERVICE_NAME}" "${PUBLISH_SERVICE_NAME}" || {
  echo "[start] Timeout or failure waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[start] WebGoat is healthy"
"${COMPOSE[@]}" ps
