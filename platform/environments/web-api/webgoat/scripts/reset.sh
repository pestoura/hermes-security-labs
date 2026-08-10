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

echo "[reset] Disconnecting Kali..."
docker network disconnect webgoat-lab hermes-kali-mcp 2>/dev/null || true

echo "[reset] Tearing down project with volumes..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[reset] Recreating lab..."
"${COMPOSE[@]}" up -d

echo "[reset] Waiting for healthy application and publication services (timeout ${HEALTH_TIMEOUT_SECONDS}s)..."
wait_for_services_healthy "reset" "${HEALTH_TIMEOUT_SECONDS}" "${SERVICE_NAME}" "${PUBLISH_SERVICE_NAME}" || {
  echo "[reset] Timeout or failure waiting for healthy"
  "${COMPOSE[@]}" logs --tail 50
  exit 1
}

echo "[reset] Running smoke..."
"${SCRIPT_DIR}/smoke.sh"

echo "[reset] Lab reset complete (Kali remains disconnected)"
