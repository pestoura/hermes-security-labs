#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="juice-shop"
NETWORK_NAME="juice-shop_juice-shop-lab"
CONTAINER_NAME="juice-shop"
DATA_VOLUME="juice-shop_juice-shop-data"
FTP_VOLUME="juice-shop_juice-shop-ftp"

COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

# Trap to ensure Kali is disconnected even on failure
cleanup_kali() {
  docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp 2>/dev/null || true
}
trap cleanup_kali EXIT

echo "[destroy] Disconnecting Kali MCP..."
docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp 2>/dev/null || true

echo "[destroy] Removing project containers, volumes, and network..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[destroy] Verifying cleanup..."

# Check container
if docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: Container still exists"
  exit 1
else
  echo "[destroy] Container removed"
fi

# Check volumes
if docker volume inspect "${DATA_VOLUME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: Data volume still exists"
  exit 1
else
  echo "[destroy] Data volume removed"
fi

if docker volume inspect "${FTP_VOLUME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: FTP volume still exists"
  exit 1
else
  echo "[destroy] FTP volume removed"
fi

# Check network
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  # Get endpoints
  ENDPOINTS="$(docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null || true)"
  if [ -n "${ENDPOINTS}" ]; then
    echo "[destroy] ERROR: Network still has endpoints: ${ENDPOINTS}"
    exit 1
  fi

  # Check if it's our project's network
  PROJECT_LABEL="$(docker network inspect "${NETWORK_NAME}" --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
  if [ "${PROJECT_LABEL}" != "${PROJECT_NAME}" ]; then
    echo "[destroy] ERROR: Refusing to remove network not owned by project"
    exit 1
  fi

  # Remove the empty network
  docker network rm "${NETWORK_NAME}"
  echo "[destroy] Network removed"
else
  echo "[destroy] Network removed"
fi

# Final verification
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: Network still exists"
  exit 1
fi

echo "[destroy] Destroy complete"
