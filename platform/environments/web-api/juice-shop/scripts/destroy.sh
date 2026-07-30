#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

# Get project name from compose
PROJECT_NAME=$(docker compose -f "${COMPOSE_FILE}" config --format json | jq -r '.name // "juice-shop"')
NETWORK_NAME="${PROJECT_NAME}_juice-shop-lab"

# Trap to ensure Kali is disconnected even on failure
cleanup_kali() {
  docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp 2>/dev/null || true
}
trap cleanup_kali EXIT

echo "[destroy] Disconnecting Kali MCP..."
docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp 2>/dev/null || true

echo "[destroy] Removing project containers, volumes, and network..."
docker compose -f "${COMPOSE_FILE}" down --volumes --remove-orphans

echo "[destroy] Verifying cleanup..."
# Check container
if docker ps -a --filter "name=juice-shop" --format "{{.Names}}" | grep -q juice-shop; then
  echo "[destroy] ERROR: Container still exists"
  exit 1
else
  echo "[destroy] Container removed"
fi

# Check volumes
if docker volume ls --filter "name=juice-shop" --format "{{.Name}}" | grep -q juice-shop; then
  echo "[destroy] ERROR: Volumes still exist"
  exit 1
else
  echo "[destroy] Volumes removed"
fi

# Check network (project network should be removed)
if docker network ls --filter "name=${NETWORK_NAME}" --format "{{.Name}}" | grep -q "${NETWORK_NAME}"; then
  # Check if any external containers are still using it
  ENDPOINTS=$(docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null || true)
  if [ -n "$ENDPOINTS" ]; then
    echo "[destroy] ERROR: Network still has endpoints: ${ENDPOINTS}"
    exit 1
  else
    echo "[destroy] Network removed"
  fi
else
  echo "[destroy] Network removed"
fi

echo "[destroy] Destroy complete"
