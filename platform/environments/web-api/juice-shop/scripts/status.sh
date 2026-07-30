#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

# Get the project name from compose
PROJECT_NAME=$(docker compose -f "${COMPOSE_FILE}" config --format json | jq -r '.name // "juice-shop"')
NETWORK_NAME="${PROJECT_NAME}_juice-shop-lab"

echo "[status] Compose state:"
docker compose -f "${COMPOSE_FILE}" ps

echo ""
echo "[status] Container health:"
docker inspect -f "{{.State.Health.Status}}" juice-shop 2>/dev/null || echo "Container not found"

echo ""
echo "[status] Port mapping:"
docker port juice-shop 2>/dev/null || echo "No ports published"

echo ""
echo "[status] Network:"
docker network inspect "${NETWORK_NAME}" --format '{{.Name}} {{.Driver}} {{.Scope}}' 2>/dev/null || echo "Network not found: ${NETWORK_NAME}"

echo ""
echo "[status] Kali MCP in ${NETWORK_NAME}:"
docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | grep -q hermes-kali-mcp && echo "CONNECTED" || echo "NOT CONNECTED"
