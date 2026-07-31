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
KALI_CONTAINER="hermes-kali-mcp"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

service_report() {
  local service="$1"
  local id
  id="$("${COMPOSE[@]}" ps -q "${service}" 2>/dev/null || true)"

  if [[ -z "${id}" ]]; then
    printf '%s: ABSENT\n' "${service}"
    return
  fi

  local name state health image
  name="$(docker inspect "${id}" --format '{{.Name}}' | sed 's#^/##')"
  state="$(docker inspect "${id}" --format '{{.State.Status}}')"
  health="$(docker inspect "${id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  image="$(docker inspect "${id}" --format '{{.Config.Image}}')"

  printf '%s: name=%s id=%s state=%s health=%s image=%s\n' \
    "${service}" "${name}" "${id}" "${state}" "${health}" "${image}"
}

network_report() {
  local network="$1"
  if ! docker network inspect "${network}" >/dev/null 2>&1; then
    printf 'network %s: ABSENT\n' "${network}"
    return
  fi

  docker network inspect "${network}" \
    --format 'network {{.Name}}: driver={{.Driver}} internal={{.Internal}} project={{index .Labels "com.docker.compose.project"}} endpoints={{range .Containers}}{{.Name}} {{end}}'
}

echo "Project: ${PROJECT_NAME}"
"${COMPOSE[@]}" ps || true
service_report "${APP_SERVICE}"
service_report "${DB_SERVICE}"

app_mapping="$("${COMPOSE[@]}" port "${APP_SERVICE}" 80 2>/dev/null || true)"
printf 'DVWA host mapping: %s\n' "${app_mapping:-ABSENT}"

app_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}" 2>/dev/null || true)"
db_id="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}" 2>/dev/null || true)"

if [[ -n "${db_id}" ]]; then
  db_bindings="$(docker inspect "${db_id}" --format '{{json .HostConfig.PortBindings}}')"
  printf 'MariaDB host bindings: %s\n' "${db_bindings}"
fi

network_report "${APP_NETWORK}"
network_report "${DB_NETWORK}"

if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  docker volume inspect "${VOLUME_NAME}" \
    --format 'volume {{.Name}}: project={{index .Labels "com.docker.compose.project"}}'
else
  printf 'volume %s: ABSENT\n' "${VOLUME_NAME}"
fi

if docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
  kali_networks="$(docker inspect "${KALI_CONTAINER}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"
  if grep -qw "${APP_NETWORK}" <<<"${kali_networks}"; then
    echo "Kali: CONNECTED to ${APP_NETWORK}"
  else
    echo "Kali: NOT CONNECTED to ${APP_NETWORK}"
  fi
  printf 'Kali networks: %s\n' "${kali_networks}"
else
  echo "Kali: container absent"
fi

if [[ -n "${app_id}" ]]; then
  printf 'Authorised internal target: http://dvwa:80/login.php\n'
fi
