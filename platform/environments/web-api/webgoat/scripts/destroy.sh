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

cleanup_kali() {
  docker network disconnect \
    "${NETWORK_NAME}" \
    "${KALI_CONTAINER}" \
    >/dev/null 2>&1 || true
}

trap cleanup_kali EXIT

mapfile -t CONTAINER_IDS < <(
  "${COMPOSE[@]}" ps -aq "${SERVICE_NAME}" 2>/dev/null || true
)

cleanup_kali

KALI_NETWORKS="$(
  docker inspect "${KALI_CONTAINER}" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
    2>/dev/null || true
)"
if grep -qw "${NETWORK_NAME}" <<<"${KALI_NETWORKS}"; then
  echo "[destroy] ERROR: Kali is still connected to ${NETWORK_NAME}"
  exit 1
fi

echo "[destroy] Tearing down project with volumes and orphans..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "[destroy] Validating container absence..."
for container_id in "${CONTAINER_IDS[@]}"; do
  [ -n "${container_id}" ] || continue
  if docker container inspect "${container_id}" >/dev/null 2>&1; then
    echo "[destroy] ERROR: container ${container_id} still exists"
    exit 1
  fi
done

if "${COMPOSE[@]}" ps -aq "${SERVICE_NAME}" 2>/dev/null | grep -q .; then
  echo "[destroy] ERROR: project service container still exists"
  exit 1
fi
echo "[destroy] Container absent: OK"

echo "[destroy] Validating volume absence..."
if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: volume ${VOLUME_NAME} still exists"
  exit 1
fi
echo "[destroy] Volume absent: OK"

echo "[destroy] Validating network absence..."
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  ENDPOINTS="$(
    docker network inspect "${NETWORK_NAME}" \
      --format '{{range .Containers}}{{.Name}} {{end}}'
  )"

  if [ -n "${ENDPOINTS}" ]; then
    echo "[destroy] ERROR: network still has endpoints: ${ENDPOINTS}"
    exit 1
  fi

  PROJECT_LABEL="$(
    docker network inspect "${NETWORK_NAME}" \
      --format '{{index .Labels "com.docker.compose.project"}}'
  )"

  if [ "${PROJECT_LABEL}" != "${PROJECT_NAME}" ]; then
    echo "[destroy] ERROR: refusing to remove foreign network"
    exit 1
  fi

  echo "[destroy] Removing empty project network..."
  docker network rm "${NETWORK_NAME}" >/dev/null
fi

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[destroy] ERROR: network still exists"
  exit 1
fi
echo "[destroy] Network absent: OK"

echo "[destroy] Validating Kali state..."
KALI_STATUS="$(
  docker inspect "${KALI_CONTAINER}" \
    --format '{{.State.Status}}' \
    2>/dev/null || true
)"
if [ "${KALI_STATUS}" != "running" ]; then
  echo "[destroy] ERROR: Kali is not running"
  exit 1
fi

KALI_NETWORKS="$(
  docker inspect "${KALI_CONTAINER}" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
    2>/dev/null || true
)"
if grep -qw "${NETWORK_NAME}" <<<"${KALI_NETWORKS}"; then
  echo "[destroy] ERROR: Kali is still connected"
  exit 1
fi

echo "[destroy] Kali status: running"
echo "[destroy] Kali disconnected: OK"
echo "[destroy] Image preserved"
echo "[destroy] All validations passed"
