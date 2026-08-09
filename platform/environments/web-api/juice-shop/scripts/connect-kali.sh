#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="juice-shop"
APP_SERVICE="juice-shop"
APP_NETWORK="juice-shop-lab"
KALI_CONTAINER="hermes-kali-mcp"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

fail() {
  echo "[connect-kali] FAIL: $*" >&2
  exit 1
}

kali_state="$(docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null || true)"
[[ "${kali_state}" == running ]] || fail "${KALI_CONTAINER} is not running"

docker network inspect "${APP_NETWORK}" >/dev/null 2>&1 || fail "${APP_NETWORK} is absent"
project_label="$(docker network inspect "${APP_NETWORK}" --format '{{index .Labels "com.docker.compose.project"}}')"
[[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "${APP_NETWORK} is not owned by ${PROJECT_NAME}"

app_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}" 2>/dev/null || true)"
[[ -n "${app_id}" ]] || fail "Juice Shop container is absent"
app_state="$(docker inspect "${app_id}" --format '{{.State.Status}}')"
[[ "${app_state}" == running ]] || fail "Juice Shop container is not running"
app_name="$(docker inspect "${app_id}" --format '{{.Name}}' | sed 's#^/##')"

endpoint_names="$(docker network inspect "${APP_NETWORK}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
app_present=false
kali_present=false
while IFS= read -r endpoint; do
  [[ -z "${endpoint}" ]] && continue
  case "${endpoint}" in
    "${app_name}") app_present=true ;;
    "${KALI_CONTAINER}") kali_present=true ;;
    *) fail "unexpected endpoint ${endpoint} on ${APP_NETWORK}" ;;
  esac
done <<<"${endpoint_names}"

[[ "${app_present}" == true ]] || fail "expected Juice Shop endpoint ${app_name} is missing"

if [[ "${kali_present}" == true ]]; then
  echo "[connect-kali] ALREADY CONNECTED"
  echo "[connect-kali] Authorised target: http://juice-shop:3000/"
  exit 0
fi

echo "[connect-kali] Connecting ${KALI_CONTAINER} to ${APP_NETWORK}..."
docker network connect "${APP_NETWORK}" "${KALI_CONTAINER}"

endpoint_names="$(docker network inspect "${APP_NETWORK}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
grep -Fxq "${KALI_CONTAINER}" <<<"${endpoint_names}" || fail "connection verification failed"

echo "[connect-kali] CONNECTED"
echo "[connect-kali] Authorised target: http://juice-shop:3000/"
