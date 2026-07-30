#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

# Trap to ensure Kali is disconnected even on failure
cleanup_kali() {
  docker network disconnect juice-shop-lab hermes-kali-mcp 2>/dev/null || true
}
trap cleanup_kali EXIT

echo "[destroy] Disconnecting Kali MCP..."
docker network disconnect juice-shop-lab hermes-kali-mcp 2>/dev/null || true

echo "[destroy] Removing project containers, volumes, and network..."
docker compose -f "${COMPOSE_FILE}" down --volumes --remove-orphans

echo "[destroy] Verifying cleanup..."
docker ps -a --filter "name=juice-shop" --format "{{.Names}}" | grep -q juice-shop && {
  echo "[destroy] ERROR: Container still exists"
  exit 1
} || echo "[destroy] Container removed"

docker network ls --filter "name=juice-shop-lab" --format "{{.Name}}" | grep -q juice-shop-lab && {
  echo "[destroy] Network still exists (may be external)"
} || echo "[destroy] Network removed"

echo "[destroy] Destroy complete"
