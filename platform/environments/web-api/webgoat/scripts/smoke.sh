#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

WEBGOAT_HOST_PORT="${WEBGOAT_HOST_PORT:-8080}"
WEBWOLF_HOST_PORT="${WEBWOLF_HOST_PORT:-9090}"

echo "[smoke] Checking container status..."
"${COMPOSE[@]}" ps

echo "[smoke] Checking health status..."
CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}" 2>/dev/null)
if [ -z "${CONTAINER_ID}" ]; then
  echo "[smoke] Container not found"
  exit 1
fi

health=$(docker inspect -f "{{.State.Health.Status}}" "${CONTAINER_ID}" 2>/dev/null || echo "none")
if [ "$health" != "healthy" ]; then
  echo "[smoke] Container not healthy: $health"
  exit 1
fi
echo "[smoke] Health: $health"

echo "[smoke] Testing WebGoat HTTP connectivity..."
curl -sf "http://127.0.0.1:${WEBGOAT_HOST_PORT}/WebGoat/" > /dev/null 2>&1 && \
  echo "[smoke] WebGoat HTTP OK" || {
  echo "[smoke] WebGoat HTTP test failed"
  exit 1
}

echo "[smoke] Testing WebWolf HTTP connectivity..."
curl -sf "http://127.0.0.1:${WEBWOLF_HOST_PORT}/login" > /dev/null 2>&1 && \
  echo "[smoke] WebWolf HTTP OK" || {
  echo "[smoke] WebWolf HTTP test failed"
  exit 1
}

echo "[smoke] Verifying localhost-only binding..."
docker inspect "${CONTAINER_ID}" --format '{{json .HostConfig.PortBindings}}' | \
  jq -r 'to_entries[] | "\(.key) -> \(.value[0].HostIp):\(.value[0].HostPort)"' | \
  grep -E "^8080/tcp -> 127.0.0.1:|^9090/tcp -> 127.0.0.1:" > /dev/null && \
  echo "[smoke] Binding is localhost-only" || {
  echo "[smoke] Binding check failed"
  exit 1
}

echo "[smoke] Verifying image digest..."
DIGEST=$(docker inspect "${CONTAINER_ID}" --format '{{.Config.Image}}')
if [[ "${DIGEST}" == *"sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7" ]]; then
  echo "[smoke] Image digest matches"
else
  echo "[smoke] Image digest mismatch: ${DIGEST}"
  exit 1
fi

echo "[smoke] Verifying network..."
docker network inspect webgoat-lab --format '{{.Name}} {{.Driver}} {{.Internal}}' | \
  grep -q 'webgoat-lab bridge' && echo "[smoke] Network OK" || {
  echo "[smoke] Network check failed"
  exit 1
}

echo "[smoke] All checks passed"
