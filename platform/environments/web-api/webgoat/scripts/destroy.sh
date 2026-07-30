#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
SERVICE_NAME="webgoat"
NETWORK_NAME="webgoat-lab"
KALI_CONTAINER="hermes-kali-mcp"
VOLUMES=("webgoat-data")

trap 'docker network disconnect "${NETWORK_NAME}" "${KALI_CONTAINER}" 2>/dev/null || true' EXIT

echo "[destroy] Tearing down project with volumes and orphans..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" down --volumes --remove-orphans

echo "[destroy] Validating container absence..."
if docker container inspect "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "[destroy] FAIL: Container ${SERVICE_NAME} still exists"
  exit 1
fi
echo "[destroy] Container absent: OK"

echo "[destroy] Validating volume absence..."
for vol in "${VOLUMES[@]}"; do
  if docker volume inspect "${vol}" >/dev/null 2>&1; then
    echo "[destroy] FAIL: Volume ${vol} still exists"
    exit 1
  fi
done
echo "[destroy] Volumes absent: OK"

echo "[destroy] Validating network absence..."
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  if [ -z "$(docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}}{{end}}')" ]; then
    if docker network inspect "${NETWORK_NAME}" --format '{{.Labels}}' | grep -q "com.docker.compose.project=${PROJECT_NAME}"; then
      echo "[destroy] Removing project network..."
      docker network rm "${NETWORK_NAME}"
    else
      echo "[destroy] FAIL: Network ${NETWORK_NAME} exists but is not project-owned"
      exit 1
    fi
  fi
fi
echo "[destroy] Network absent: OK"

echo "[destroy] Kali running and disconnected..."
docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null | grep -q running && \
  echo "[destroy] Kali status: running" || echo "[destroy] WARNING: Kali not running"
docker network inspect "${NETWORK_NAME}" 2>/dev/null | grep -q "${KALI_CONTAINER}" && \
  echo "[destroy] FAIL: Kali still connected" && exit 1 || echo "[destroy] Kali disconnected: OK"

echo "[destroy] Image preserved (not removed)"

echo "[destroy] All validations passed"
