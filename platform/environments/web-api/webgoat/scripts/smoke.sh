#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
# Application service: owns the pinned image digest and the workload health gate.
SERVICE_NAME="webgoat"
# Publication service: the ONLY service that declares host port mappings in
# compose.yaml, so it is also the only service `docker compose port` can resolve.
PUBLISH_SERVICE_NAME="webgoat-proxy"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[smoke] Checking container status..."
"${COMPOSE[@]}" ps

echo "[smoke] Checking health status..."
CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}" 2>/dev/null)
if [ -z "${CONTAINER_ID}" ]; then
  echo "[smoke] Container not found"
  exit 1
fi

health=$(docker inspect -f "{{.State.Health.Status}}" "${CONTAINER_ID}" 2>/dev/null || echo "none")
if [ "${health}" != "healthy" ]; then
  echo "[smoke] Container not healthy: ${health}"
  exit 1
fi
echo "[smoke] Health: ${health}"

echo "[smoke] Checking publication service health status..."
PUBLISH_CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${PUBLISH_SERVICE_NAME}" 2>/dev/null)
if [ -z "${PUBLISH_CONTAINER_ID}" ]; then
  echo "[smoke] Publication container not found: ${PUBLISH_SERVICE_NAME}"
  exit 1
fi

publish_health=$(docker inspect -f "{{.State.Health.Status}}" "${PUBLISH_CONTAINER_ID}" 2>/dev/null || echo "none")
if [ "${publish_health}" != "healthy" ]; then
  echo "[smoke] Publication container not healthy: ${publish_health}"
  exit 1
fi
echo "[smoke] Publication health: ${publish_health}"

# Get actual host port mappings from the publishing service (webgoat-proxy).
WEBGOAT_MAPPING=$("${COMPOSE[@]}" port "${PUBLISH_SERVICE_NAME}" 8080 2>/dev/null || true)
WEBWOLF_MAPPING=$("${COMPOSE[@]}" port "${PUBLISH_SERVICE_NAME}" 9090 2>/dev/null || true)

if [ -z "${WEBGOAT_MAPPING}" ] || [ -z "${WEBWOLF_MAPPING}" ]; then
  echo "[smoke] Could not determine port mappings"
  exit 1
fi

# Extract host ports from mappings (format: 127.0.0.1:8080)
WEBGOAT_PORT=$(echo "${WEBGOAT_MAPPING}" | cut -d: -f2)
WEBWOLF_PORT=$(echo "${WEBWOLF_MAPPING}" | cut -d: -f2)

echo "[smoke] WebGoat mapping: ${WEBGOAT_MAPPING}"
echo "[smoke] WebWolf mapping: ${WEBWOLF_MAPPING}"

# Verify localhost-only binding
echo "${WEBGOAT_MAPPING}" | grep -q '^127\.0\.0\.1:' || { echo "[smoke] WebGoat binding check failed"; exit 1; }
echo "${WEBWOLF_MAPPING}" | grep -q '^127\.0\.0\.1:' || { echo "[smoke] WebWolf binding check failed"; exit 1; }
echo "[smoke] Binding is localhost-only"

echo "[smoke] Testing WebGoat HTTP connectivity..."
curl -sf "http://127.0.0.1:${WEBGOAT_PORT}/WebGoat/" > /dev/null 2>&1 && \
  echo "[smoke] WebGoat HTTP OK" || {
  echo "[smoke] WebGoat HTTP test failed"
  exit 1
}

echo "[smoke] Testing WebWolf HTTP connectivity..."
curl -sf "http://127.0.0.1:${WEBWOLF_PORT}/login" > /dev/null 2>&1 && \
  echo "[smoke] WebWolf HTTP OK" || {
  echo "[smoke] WebWolf HTTP test failed"
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
docker network inspect webgoat-lab --format '{{.Name}} {{.Driver}}' | grep -q 'webgoat-lab bridge' && echo "[smoke] Network OK" || {
  echo "[smoke] Network check failed"
  exit 1
}

echo "[smoke] All checks passed"
