#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="crapi"; APP_SERVICE="crapi-web"; LAB_NETWORK="crapi-lab"; CORE_NETWORK="crapi-core"
KALI_CONTAINER="hermes-kali-mcp"; HOST_PORT="${CRAPI_HOST_PORT:-8888}"; CONTAINER_PORT="80"
SERVICES=(postgresdb mongodb mailhog gateway crapi-identity crapi-community crapi-workshop crapi-web)
INTERNAL_SERVICES=(postgresdb mongodb mailhog gateway crapi-identity crapi-community crapi-workshop)
VOLUMES=(crapi_crapi-postgres-data crapi_crapi-mongo-data)
EXPECTED_CRAPI_IMAGES=(
  crapi/crapi-identity:1.1.6-rc8@sha256:5152eaa8b25d8585068ec478c9a2ee886ce1658d8289fd047f83325737490f78
  crapi/crapi-community:1.1.6-rc8@sha256:ff62181b9089df60379c1cecdcfceb0f54ea6d6c4d7c407bb2f5fd55208f2be0
  crapi/crapi-workshop:1.1.6-rc8@sha256:b73a2e4aed1a62ba9c626214eca6b66289f2f5cced7169dbd791837edf263de6
  crapi/crapi-web:1.1.6-rc8@sha256:6cbafa5085cc38199c5f16f71ad11579168e08ca25c22e9b89f55e423caa8746
  crapi/gateway-service:1.1.6-rc8@sha256:111a996957c1e9f78fe401b4d9a16bb99e6d6a3aa836792382a52c9ecbd39c8c
  crapi/mailhog:1.1.6-rc8@sha256:c3a74b1f63673996aec82f175ad4dd49cc3152637f68dc3dfc9f765e06c0f5e9
)
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${ENV_DIR}/compose.yaml")
id(){ "${COMPOSE[@]}" ps -q "$1" 2>/dev/null; }
owned(){ docker network inspect "$1" --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null | grep -qx "${PROJECT_NAME}"; }
kali_connected(){ docker network inspect "${LAB_NETWORK}" --format '{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null | grep -qw "${KALI_CONTAINER}"; }
verify_images(){
  local effective expected
  effective="$("${COMPOSE[@]}" config --images)"
  printf '%s\n' "${effective}"
  for expected in "${EXPECTED_CRAPI_IMAGES[@]}"; do
    grep -Fxq "${expected}" <<<"${effective}" || {
      echo "[start] Effective Compose image missing: ${expected}"
      return 1
    }
  done
  if grep -E '^crapi/.+:(1\.1\.6|latest|main|develop)$' <<<"${effective}"; then
    echo '[start] Refusing mutable or incorrect crAPI image reference'
    return 1
  fi
  if grep -v '@sha256:' <<<"${effective}"; then
    echo '[start] Refusing effective image reference without an immutable digest'
    return 1
  fi
}
disconnect(){ if ! docker network inspect "${LAB_NETWORK}" >/dev/null 2>&1; then echo '[disconnect-kali] Network absent'; return 0; fi; owned "${LAB_NETWORK}" || { echo '[disconnect-kali] Refusing unowned network'; return 1; }; if kali_connected; then docker network disconnect "${LAB_NETWORK}" "${KALI_CONTAINER}"; echo '[disconnect-kali] DISCONNECTED'; else echo '[disconnect-kali] ALREADY DISCONNECTED'; fi; }
wait_healthy(){ local service cid health; for service in "${SERVICES[@]}"; do for _ in $(seq 1 120); do cid="$(id "${service}")"; if [ -n "${cid}" ]; then health="$(docker inspect "${cid}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"; [ "${health}" = healthy ] && break; [ "$(docker inspect "${cid}" --format '{{.State.Status}}')" = exited ] && return 1; fi; sleep 5; done; cid="$(id "${service}")"; [ -n "${cid}" ] && [ "$(docker inspect "${cid}" --format '{{.State.Health.Status}}')" = healthy ] || { echo "[start] ${service} not healthy"; return 1; }; done; }
start(){ "${COMPOSE[@]}" config --quiet; verify_images; if [ -z "$(id "${APP_SERVICE}")" ] && ss -ltn "sport = :${HOST_PORT}" | grep -q LISTEN; then echo "[start] Port ${HOST_PORT} already in use"; return 1; fi; "${COMPOSE[@]}" pull; "${COMPOSE[@]}" up -d; wait_healthy || { "${COMPOSE[@]}" logs --tail 150; return 1; }; echo '[start] All crAPI services healthy'; "${COMPOSE[@]}" ps; }
status(){ "${COMPOSE[@]}" ps; local s cid; for s in "${SERVICES[@]}"; do cid="$(id "${s}")"; [ -n "${cid}" ] && docker inspect "${cid}" --format "service=${s} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range \$name, \$_ := .NetworkSettings.Networks}}{{\$name}} {{end}}" || true; done; "${COMPOSE[@]}" port "${APP_SERVICE}" "${CONTAINER_PORT}" || true; if kali_connected; then echo 'Kali CONNECTED'; else echo 'Kali NOT CONNECTED'; fi; }
smoke(){ local s cid mapping code bindings; for s in "${SERVICES[@]}"; do cid="$(id "${s}")"; [ -n "${cid}" ] && [ "$(docker inspect "${cid}" --format '{{.State.Health.Status}}')" = healthy ] || return 1; done; mapping="$("${COMPOSE[@]}" port "${APP_SERVICE}" "${CONTAINER_PORT}")"; [ "${mapping}" = "127.0.0.1:${HOST_PORT}" ]; for s in "${INTERNAL_SERVICES[@]}"; do cid="$(id "${s}")"; bindings="$(docker inspect "${cid}" --format '{{json .HostConfig.PortBindings}}')"; [ "${bindings}" = '{}' ] || [ "${bindings}" = null ] || { echo "[smoke] ${s} has host binding ${bindings}"; return 1; }; done; code="$(python3 - "${HOST_PORT}" <<'PY'
import http.client,sys
c=http.client.HTTPConnection('127.0.0.1',int(sys.argv[1]),timeout=10); c.request('GET','/health'); r=c.getresponse(); print(r.status); r.read(); c.close()
PY
)"; [[ "${code}" =~ ^[234][0-9][0-9]$ ]]; owned "${LAB_NETWORK}"; owned "${CORE_NETWORK}"; [ "$(docker network inspect "${LAB_NETWORK}" --format '{{.Internal}}')" = false ]; [ "$(docker network inspect "${CORE_NETWORK}" --format '{{.Internal}}')" = true ]; ! kali_connected; echo "[smoke] PASS HTTP=${code} mapping=${mapping}"; }
connect(){ docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}' 2>/dev/null | grep -qx running; owned "${LAB_NETWORK}"; local app; app="$(id "${APP_SERVICE}")"; [ -n "${app}" ] && [ "$(docker inspect "${app}" --format '{{.State.Health.Status}}')" = healthy ]; if kali_connected; then echo '[connect-kali] ALREADY CONNECTED'; return 0; fi; docker network connect "${LAB_NETWORK}" "${KALI_CONTAINER}"; kali_connected; docker inspect "${KALI_CONTAINER}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' | grep -qw "${CORE_NETWORK}" && { echo '[connect-kali] Kali reached core network'; return 1; } || true; echo '[connect-kali] CONNECTED — authorised target http://crapi:80/'; }
stop(){ disconnect; "${COMPOSE[@]}" stop; }
destroy(){ disconnect; for n in "${LAB_NETWORK}" "${CORE_NETWORK}"; do if docker network inspect "${n}" >/dev/null 2>&1; then owned "${n}" || { echo "[destroy] Refusing unowned ${n}"; return 1; }; fi; done; "${COMPOSE[@]}" down --volumes --remove-orphans; ! "${COMPOSE[@]}" ps -aq | grep -q .; local v; for v in "${VOLUMES[@]}"; do ! docker volume inspect "${v}" >/dev/null 2>&1; done; ! docker network inspect "${LAB_NETWORK}" >/dev/null 2>&1; ! docker network inspect "${CORE_NETWORK}" >/dev/null 2>&1; echo '[destroy] COMPLETE'; }
reset(){ destroy; start; smoke; }
case "${1:-}" in start) start;; status) status;; smoke) smoke;; connect-kali) connect;; disconnect-kali) disconnect;; stop) stop;; reset) reset;; destroy) destroy;; *) echo "Usage: $0 {start|status|smoke|connect-kali|disconnect-kali|stop|reset|destroy}"; exit 2;; esac
