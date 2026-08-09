#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="juice-shop"
KALI_CONTAINER="hermes-kali-mcp"
NETWORK_NAME="juice-shop-lab"

if ! docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
  echo "[disconnect-kali] Kali container absent; nothing to do"
  exit 0
fi

if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[disconnect-kali] ${NETWORK_NAME} absent; nothing to do"
  exit 0
fi

project_label="$(docker network inspect "${NETWORK_NAME}" --format '{{index .Labels "com.docker.compose.project"}}')"
if [[ "${project_label}" != "${PROJECT_NAME}" ]]; then
  echo "[disconnect-kali] ERROR: refusing foreign network ${NETWORK_NAME}" >&2
  exit 1
fi

endpoints="$(docker network inspect "${NETWORK_NAME}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
if grep -Fxq "${KALI_CONTAINER}" <<<"${endpoints}"; then
  echo "[disconnect-kali] Disconnecting ${KALI_CONTAINER} from ${NETWORK_NAME}..."
  docker network disconnect "${NETWORK_NAME}" "${KALI_CONTAINER}"
else
  echo "[disconnect-kali] ${KALI_CONTAINER} already disconnected from ${NETWORK_NAME}"
fi

endpoints="$(docker network inspect "${NETWORK_NAME}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
if grep -Fxq "${KALI_CONTAINER}" <<<"${endpoints}"; then
  echo "[disconnect-kali] ERROR: Kali remains connected to ${NETWORK_NAME}" >&2
  exit 1
fi

echo "[disconnect-kali] KALI_DISCONNECTED=true"
