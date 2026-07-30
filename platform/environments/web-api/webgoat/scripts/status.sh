#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
NETWORK_NAME="webgoat-lab"
KALI_CONTAINER="hermes-kali-mcp"

COMPOSE=(
  docker compose
  -p "${PROJECT_NAME}"
  -f "${COMPOSE_FILE}"
)

WEBGOAT_HOST_PORT="${WEBGOAT_HOST_PORT:-8080}"
WEBWOLF_HOST_PORT="${WEBWOLF_HOST_PORT:-9090}"

echo "[status] Compose state:"
"${COMPOSE[@]}" ps

echo ""
echo "[status] Container health:"
CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}" 2>/dev/null)
if [ -n "${CONTAINER_ID}" ]; then
  docker inspect "${CONTAINER_ID}" --format '{{.State.Health.Status}}' 2>/dev/null || echo "no healthcheck"
else
  echo "Container not found"
fi

echo ""
echo "[status] Port mapping (host -> container):"
CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}" 2>/dev/null)
if [ -n "${CONTAINER_ID}" ]; then
  docker inspect "${CONTAINER_ID}" --format '{{json .HostConfig.PortBindings}}' 2>/dev/null | \
    jq -r 'to_entries[] | "\(.key) -> \(.value[0].HostIp):\(.value[0].HostPort)"' 2>/dev/null || \
    echo "No ports published"
else
  echo "Container not found"
fi

echo ""
echo "[status] Network:"
docker network inspect "${NETWORK_NAME}" --format '{{.Name}} {{.Driver}} {{.Internal}}' 2>/dev/null || echo "Network not found"

echo ""
echo "[status] Kali MCP in ${NETWORK_NAME}:"
docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | \
  grep -q "${KALI_CONTAINER}" && echo "CONNECTED" || echo "NOT CONNECTED"

echo ""
echo "[status] Volumes:"
docker volume ls --filter "label=com.docker.compose.project=${PROJECT_NAME}" --format '{{.Name}}' 2>/dev/null || echo "None"

echo ""
echo "[status] Image/digest:"
CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}" 2>/dev/null)
if [ -n "${CONTAINER_ID}" ]; then
  docker inspect "${CONTAINER_ID}" --format '{{.Config.Image}}' 2>/dev/null
fi

echo ""
echo "[status] Internal targets:"
echo "  WebGoat: http://webgoat:8080/WebGoat/"
echo "  WebWolf: http://webgoat:9090/WebWolf/"
