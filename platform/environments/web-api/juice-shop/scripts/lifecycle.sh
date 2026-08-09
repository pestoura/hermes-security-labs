#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="juice-shop"
PRIMARY_SERVICE="juice-shop"
NETWORK_NAME="juice-shop-lab"
KALI_CONTAINER="hermes-kali-mcp"
HOST_PORT="${JUICE_SHOP_HOST_PORT:-3000}"
CONTAINER_PORT="3000"
TARGET_PATH="/"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${ENV_DIR}/compose.yaml")

container_id() {
  "${COMPOSE[@]}" ps -q "${PRIMARY_SERVICE}" 2>/dev/null
}

is_kali_connected() {
  docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null |
    grep -qw "${KALI_CONTAINER}"
}

assert_network_owned() {
  docker network inspect "${NETWORK_NAME}" --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null |
    grep -qx "${PROJECT_NAME}"
}

disconnect_kali() {
  if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    echo "[disconnect-kali] Network absent"
    return 0
  fi
  assert_network_owned || { echo "[disconnect-kali] Refusing unowned network"; return 1; }
  if is_kali_connected; then
    docker network disconnect "${NETWORK_NAME}" "${KALI_CONTAINER}"
    echo "[disconnect-kali] DISCONNECTED"
  else
    echo "[disconnect-kali] ALREADY DISCONNECTED"
  fi
}

start_lab() {
  "${COMPOSE[@]}" config --quiet
  local existing
  existing="$(container_id)"
  if [ -z "${existing}" ] && ss -ltn "sport = :${HOST_PORT}" | grep -q LISTEN; then
    echo "[start] Port ${HOST_PORT} already in use"
    return 1
  fi
  "${COMPOSE[@]}" up -d --pull missing
  local id health
  for _ in $(seq 1 48); do
    id="$(container_id)"
    if [ -n "${id}" ]; then
      health="$(docker inspect "${id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
      [ "${health}" = healthy ] && { echo "[start] Healthy"; "${COMPOSE[@]}" ps; return 0; }
      [ "$(docker inspect "${id}" --format '{{.State.Status}}')" = exited ] && break
    fi
    sleep 5
  done
  "${COMPOSE[@]}" logs --tail 100
  return 1
}

status_lab() {
  "${COMPOSE[@]}" ps
  local id
  id="$(container_id)"
  [ -n "${id}" ] || { echo "[status] STOPPED"; return 0; }
  docker inspect "${id}" --format 'state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
  "${COMPOSE[@]}" port "${PRIMARY_SERVICE}" "${CONTAINER_PORT}" || true
  if is_kali_connected; then echo "Kali CONNECTED"; else echo "Kali NOT CONNECTED"; fi
}

smoke_lab() {
  local id mapping status
  id="$(container_id)"
  [ -n "${id}" ] || { echo "[smoke] Container absent"; return 1; }
  [ "$(docker inspect "${id}" --format '{{.State.Health.Status}}')" = healthy ]
  mapping="$("${COMPOSE[@]}" port "${PRIMARY_SERVICE}" "${CONTAINER_PORT}")"
  [ "${mapping}" = "127.0.0.1:${HOST_PORT}" ] || { echo "[smoke] Unexpected mapping ${mapping}"; return 1; }
  status="$(python3 - "${HOST_PORT}" "${TARGET_PATH}" <<'PY'
import http.client, sys
c=http.client.HTTPConnection('127.0.0.1', int(sys.argv[1]), timeout=5)
c.request('GET', sys.argv[2]); r=c.getresponse(); print(r.status); r.read(); c.close()
PY
)"
  [[ "${status}" =~ ^[234][0-9][0-9]$ ]] || { echo "[smoke] HTTP ${status}"; return 1; }
  assert_network_owned
  [ "$(docker network inspect "${NETWORK_NAME}" --format '{{.Internal}}')" = false ]
  ! is_kali_connected
  echo "[smoke] PASS HTTP=${status} mapping=${mapping}"
}

connect_kali() {
  docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null | grep -qx running
  assert_network_owned
  local id
  id="$(container_id)"
  [ -n "${id}" ] && [ "$(docker inspect "${id}" --format '{{.State.Status}}')" = running ]
  if is_kali_connected; then echo "[connect-kali] ALREADY CONNECTED"; return 0; fi
  docker network connect "${NETWORK_NAME}" "${KALI_CONTAINER}"
  is_kali_connected
  echo "[connect-kali] CONNECTED — authorised target http://juice-shop:3000/"
}

stop_lab() {
  disconnect_kali
  "${COMPOSE[@]}" stop
}

destroy_lab() {
  disconnect_kali
  "${COMPOSE[@]}" down --volumes --remove-orphans
  ! "${COMPOSE[@]}" ps -aq | grep -q .
  ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1
  echo "[destroy] COMPLETE"
}

reset_lab() {
  destroy_lab
  start_lab
  smoke_lab
}

case "${1:-}" in
  start) start_lab ;;
  status) status_lab ;;
  smoke) smoke_lab ;;
  connect-kali) connect_kali ;;
  disconnect-kali) disconnect_kali ;;
  stop) stop_lab ;;
  reset) reset_lab ;;
  destroy) destroy_lab ;;
  *) echo "Usage: $0 {start|status|smoke|connect-kali|disconnect-kali|stop|reset|destroy}"; exit 2 ;;
esac
