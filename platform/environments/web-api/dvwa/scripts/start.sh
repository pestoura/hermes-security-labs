#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="dvwa"
APP_SERVICE="dvwa"
DB_SERVICE="db"
APP_NETWORK="dvwa-lab"
DB_NETWORK="dvwa-db"
VOLUME_NAME="dvwa_dvwa-db-data"
DVWA_HOST_PORT="${DVWA_HOST_PORT:-4280}"
DVWA_IMAGE="ghcr.io/digininja/dvwa:d45ba3c@sha256:091498cedec31b4a3091a1262e6a5a0ce5ec32d4bd26486558818346ccc89d67"
DB_IMAGE="docker.io/library/mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

fail() {
  echo "[start] ERROR: $*" >&2
  exit 1
}

verify_owned_network() {
  local network="$1"
  if ! docker network inspect "${network}" >/dev/null 2>&1; then
    return 0
  fi

  local project_label
  project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
  [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing foreign network ${network}"
}

verify_owned_volume() {
  if ! docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
    return 0
  fi

  local project_label
  project_label="$(docker volume inspect "${VOLUME_NAME}" --format '{{index .Labels "com.docker.compose.project"}}')"
  [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing foreign volume ${VOLUME_NAME}"
}

echo "[start] Validating Compose configuration..."
"${COMPOSE[@]}" config --quiet

verify_owned_network "${APP_NETWORK}"
verify_owned_network "${DB_NETWORK}"
verify_owned_volume

existing_app_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}" 2>/dev/null || true)"
if [[ -z "${existing_app_id}" ]] && ss -ltn "sport = :${DVWA_HOST_PORT}" | grep -q LISTEN; then
  fail "localhost port ${DVWA_HOST_PORT} is already in use"
fi

for image in "${DVWA_IMAGE}" "${DB_IMAGE}"; do
  if ! docker image inspect "${image}" >/dev/null 2>&1; then
    echo "[start] Pulling missing pinned image ${image}..."
    "${COMPOSE[@]}" pull
    break
  fi
done

echo "[start] Starting DVWA and MariaDB..."
"${COMPOSE[@]}" up -d

app_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}")"
db_id="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}")"
[[ -n "${app_id}" ]] || fail "DVWA container was not created"
[[ -n "${db_id}" ]] || fail "MariaDB container was not created"

echo "[start] Waiting for both services to become healthy..."
deadline=$((SECONDS + 240))
while (( SECONDS < deadline )); do
  app_state="$(docker inspect "${app_id}" --format '{{.State.Status}}' 2>/dev/null || echo missing)"
  db_state="$(docker inspect "${db_id}" --format '{{.State.Status}}' 2>/dev/null || echo missing)"
  app_health="$(docker inspect "${app_id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || echo missing)"
  db_health="$(docker inspect "${db_id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || echo missing)"

  printf '[start] app=%s/%s db=%s/%s\n' "${app_state}" "${app_health}" "${db_state}" "${db_health}"

  if [[ "${app_health}" == healthy && "${db_health}" == healthy ]]; then
    echo "[start] DVWA and MariaDB are healthy"
    "${COMPOSE[@]}" ps
    exit 0
  fi

  if [[ "${app_state}" == exited || "${db_state}" == exited ]]; then
    break
  fi

  sleep 5
done

echo "[start] Health wait failed; recent logs follow" >&2
"${COMPOSE[@]}" logs --tail 80 >&2 || true
exit 1
