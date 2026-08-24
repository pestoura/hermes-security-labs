#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="juice-shop"
APP_SERVICE="juice-shop"
APP_NETWORK="juice-shop-lab"
KALI_CONTAINER="hermes-kali-mcp"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[smoke] Checking container status..."
"${COMPOSE[@]}" ps

echo "[smoke] Checking health status..."
container_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}" 2>/dev/null || true)"
if [ -z "${container_id}" ]; then
  echo "[smoke] Container not found"
  exit 1
fi
health=$(docker inspect -f "{{.State.Health.Status}}" "${container_id}" 2>/dev/null || echo "none")
if [ "$health" != "healthy" ]; then
  echo "[smoke] Container not healthy: $health"
  exit 1
fi
echo "[smoke] Health: $health"

echo "[smoke] Checking network ownership and Kali isolation..."
if ! docker network inspect "${APP_NETWORK}" >/dev/null 2>&1; then
  echo "[smoke] Network absent: ${APP_NETWORK}"
  exit 1
fi
project_label="$(docker network inspect "${APP_NETWORK}" --format '{{index .Labels "com.docker.compose.project"}}')"
if [[ "${project_label}" != "${PROJECT_NAME}" ]]; then
  echo "[smoke] Network ${APP_NETWORK} is not owned by ${PROJECT_NAME}"
  exit 1
fi
app_name="$(docker inspect "${container_id}" --format '{{.Name}}' | sed 's#^/##')"
endpoint_names="$(docker network inspect "${APP_NETWORK}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
app_present=false
while IFS= read -r endpoint; do
  [[ -z "${endpoint}" ]] && continue
  case "${endpoint}" in
    "${app_name}") app_present=true ;;
    "${KALI_CONTAINER}")
      echo "[smoke] Kali must be disconnected before smoke validation"
      exit 1
      ;;
    *)
      echo "[smoke] Unexpected endpoint ${endpoint} on ${APP_NETWORK}"
      exit 1
      ;;
  esac
done <<<"${endpoint_names}"
if [[ "${app_present}" != true ]]; then
  echo "[smoke] Expected Juice Shop endpoint ${app_name} is missing"
  exit 1
fi

echo "[smoke] Resolving canonical host publication..."
mapping="$("${COMPOSE[@]}" port "${APP_SERVICE}" 3000 2>/dev/null || true)"
if [[ ! "${mapping}" =~ ^127\.0\.0\.1:([0-9]+)$ ]]; then
  echo "[smoke] Invalid or non-loopback mapping: ${mapping:-absent}"
  exit 1
fi
host_port="${BASH_REMATCH[1]}"
echo "[smoke] Mapping: ${mapping}"

echo "[smoke] Testing HTTP connectivity..."
python3 - "${host_port}" <<'PY'
import http.client
import sys

port = int(sys.argv[1])
connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
try:
    connection.request("GET", "/")
    response = connection.getresponse()
    ok = 200 <= response.status < 500
    response.read()
    if not ok:
        raise SystemExit(1)
finally:
    connection.close()
PY

echo "[smoke] HTTP OK"
echo "[smoke] All checks passed"
