#!/usr/bin/env bash
set -euo pipefail

KALI_CONTAINER="hermes-kali-mcp"
NETWORK_NAME="webgoat-lab"
SERVICE_NAME="webgoat"

echo "[connect-kali] Verifying ${KALI_CONTAINER} exists and is running..."
docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null | grep -q running || {
  echo "[connect-kali] FAIL: ${KALI_CONTAINER} not running"
  exit 1
}

echo "[connect-kali] Verifying ${NETWORK_NAME} belongs to project..."
docker network inspect "${NETWORK_NAME}" --format '{{json .Labels}}' 2>/dev/null | \
  jq -e '.["com.docker.compose.project"] == "webgoat"' > /dev/null || {
  echo "[connect-kali] FAIL: Network ${NETWORK_NAME} not owned by project"
  exit 1
}

echo "[connect-kali] Verifying only ${SERVICE_NAME} initially connected..."
connected=$(docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null)
echo "[connect-kali] Connected containers: '${connected}'"
CONTAINER_NAME="webgoat-webgoat-1"
if [[ "${connected}" != *"${CONTAINER_NAME}"* ]]; then
  echo "[connect-kali] FAIL: Expected container ${CONTAINER_NAME} not found"
  exit 1
fi
# Remove the expected container name and trim whitespace
other=$(echo "${connected}" | sed "s/${CONTAINER_NAME}//g" | tr -d ' \t\n\r')
if [[ -n "${other}" ]]; then
  echo "[connect-kali] FAIL: Unexpected endpoints: ${other}"
  exit 1
fi

echo "[connect-kali] Connecting ${KALI_CONTAINER} to ${NETWORK_NAME}..."
docker network connect "${NETWORK_NAME}" "${KALI_CONTAINER}" 2>/dev/null || true

echo "[connect-kali] Verifying connection..."
docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | \
  grep -q "${KALI_CONTAINER}" && echo "[connect-kali] CONNECTED" || {
  echo "[connect-kali] FAIL: Kali not connected"
  exit 1
}

echo "[connect-kali] Authorized internal targets:"
echo "  http://webgoat:8080/WebGoat/"
echo "  http://webgoat:9090/WebWolf/"
