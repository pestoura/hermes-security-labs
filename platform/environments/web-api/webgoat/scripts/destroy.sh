#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
NETWORK_NAME="webgoat-lab"
KALI_CONTAINER="hermes-kali-mcp"
VOLUME_NAME="webgoat_webgoat-data"

COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[destroy] Tearing down project with volumes and orphans..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[destroy] Validating container absence..."
CONTAINER_ID=$("${COMPOSE[@]}" ps -aq "${SERVICE_NAME}" 2>/dev/null || true)
if [ -n "${CONTAINER_ID}" ]; then
  if docker container inspect "${CONTAINER_ID}" >/dev/null 2>&1; then
    echo "[destroy] FAIL: Container ${SERVICE_NAME} still exists"
    exit 1
  fi
fi
echo "[destroy] Container absent: OK"

echo "[destroy] Validating volume absence..."
if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  echo "[destroy] FAIL: Volume ${VOLUME_NAME} still exists"
  exit 1
fi
echo "[destroy] Volumes absent: OK"

echo "[destroy] Validating network absence..."
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  ENDPOINTS=$(
    docker network inspect "${NETWORK_NAME}" \
      --format '{{range .Containers}}{{.Name}} {{end}}'
  )
  if [ -n "${ENDPOINTS}" ]; then
    echo "[destroy] ERROR: network still has endpoints: ${ENDPOINTS}"
    exit 1
  fi

  PROJECT_LABEL=$(
    docker network inspect "${NETWORK_NAME}" \
      --format '{{index .Labels "com.docker.compose.project"}}'
  )

  if [ "${PROJECT_LABEL}" != "${PROJECT_NAME}" ]; then
    echo "[destroy] ERROR: refusing to remove foreign network"
    exit 1
  fi

  echo "[destroy] Removing project network..."
  docker network rm "${NETWORK_NAME}"
fi

# Final verification
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: network still exists"
  exit 1
fi
echo "[destroy] Network absent: OK"

echo "[destroy] Kali running and disconnected..."
docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null | grep -q running && \
  echo "[destroy] Kali status: running" || echo "[destroy] WARNING: Kali not running"
docker network inspect "${NETWORK_NAME}" 2>/dev/null | grep -q "${KALI_CONTAINER}" && \
  { echo "[destroy] FAIL: Kali still connected"; exit 1; } || \
  echo "[destroy] Kali disconnected: OK"

echo "[destroy] Image preserved (not removed)"

echo "[destroy] All validations passed"
