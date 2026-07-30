#!/usr/bin/env bash
set -euo pipefail

KALI_CONTAINER="hermes-kali-mcp"
NETWORK_NAME="webgoat-lab"

echo "[disconnect-kali] Disconnecting ${KALI_CONTAINER} from ${NETWORK_NAME}..."
docker network disconnect "${NETWORK_NAME}" "${KALI_CONTAINER}" 2>/dev/null || true

echo "[disconnect-kali] Verifying disconnect..."
docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | \
  grep -q "${KALI_CONTAINER}" && {
  echo "[disconnect-kali] FAIL: Kali still connected"
  exit 1
} || echo "[disconnect-kali] CONFIRMED: Kali disconnected"

echo "[disconnect-kali] Kali container status:"
docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null || echo "Not found"

echo "[disconnect-kali] Other Kali networks preserved:"
docker inspect "${KALI_CONTAINER}" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null | \
  jq -r 'keys[]' 2>/dev/null || true
