#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="juice-shop"
APP_SERVICE="juice-shop"
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
