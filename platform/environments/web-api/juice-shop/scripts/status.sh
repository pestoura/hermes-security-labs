#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

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
docker network inspect juice-shop-lab --format '{{.Name}} {{.Driver}} {{.Scope}}' 2>/dev/null || echo "Network not found"

echo ""
echo "[status] Kali MCP in juice-shop-lab:"
docker network inspect juice-shop-lab --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | grep -q hermes-kali-mcp && echo "CONNECTED" || echo "NOT CONNECTED"
