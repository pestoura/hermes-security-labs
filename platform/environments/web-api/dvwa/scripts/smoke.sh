#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="dvwa"
APP_SERVICE="dvwa"
DB_SERVICE="db"
APP_NETWORK="dvwa-lab"
DB_NETWORK="dvwa-db"
KALI_CONTAINER="hermes-kali-mcp"
DVWA_IMAGE="ghcr.io/digininja/dvwa:d45ba3c@sha256:091498cedec31b4a3091a1262e6a5a0ce5ec32d4bd26486558818346ccc89d67"
DB_IMAGE="docker.io/library/mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350"
EVIDENCE_DIR="${EVIDENCE_DIR:-${REPO_ROOT}/.runtime/evidence/dvwa}"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

fail() {
  echo "[smoke] FAIL: $*" >&2
  exit 1
}

mkdir -p "${EVIDENCE_DIR}"

app_id="$("${COMPOSE[@]}" ps -q "${APP_SERVICE}" 2>/dev/null || true)"
db_id="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}" 2>/dev/null || true)"
[[ -n "${app_id}" ]] || fail "DVWA container is absent"
[[ -n "${db_id}" ]] || fail "MariaDB container is absent"

app_health="$(docker inspect "${app_id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
db_health="$(docker inspect "${db_id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
[[ "${app_health}" == healthy ]] || fail "DVWA health is ${app_health}"
[[ "${db_health}" == healthy ]] || fail "MariaDB health is ${db_health}"

mapping="$("${COMPOSE[@]}" port "${APP_SERVICE}" 80)"
[[ "${mapping}" == 127.0.0.1:* ]] || fail "DVWA mapping is not loopback-only: ${mapping}"
host_port="${mapping##*:}"
[[ "${host_port}" =~ ^[0-9]+$ ]] || fail "cannot parse DVWA host port from ${mapping}"

http_code="$(python3 - "${host_port}" <<'PY'
import http.client
import sys

port = int(sys.argv[1])
connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
try:
    connection.request("GET", "/login.php")
    response = connection.getresponse()
    print(response.status)
    response.read()
finally:
    connection.close()
PY
)" || fail "HTTP request failed"

[[ "${http_code}" =~ ^[234][0-9][0-9]$ ]] || fail "unexpected HTTP status ${http_code}"

app_image="$(docker inspect "${app_id}" --format '{{.Config.Image}}')"
db_image="$(docker inspect "${db_id}" --format '{{.Config.Image}}')"
[[ "${app_image}" == "${DVWA_IMAGE}" ]] || fail "unexpected DVWA image ${app_image}"
[[ "${db_image}" == "${DB_IMAGE}" ]] || fail "unexpected MariaDB image ${db_image}"

db_bindings="$(docker inspect "${db_id}" --format '{{json .HostConfig.PortBindings}}')"
[[ "${db_bindings}" == "{}" || "${db_bindings}" == "null" ]] || fail "MariaDB has host bindings: ${db_bindings}"

for network in "${APP_NETWORK}" "${DB_NETWORK}"; do
  docker network inspect "${network}" >/dev/null 2>&1 || fail "network ${network} is absent"
  project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
  [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "network ${network} is not owned by ${PROJECT_NAME}"
done

app_internal="$(docker network inspect "${APP_NETWORK}" --format '{{.Internal}}')"
db_internal="$(docker network inspect "${DB_NETWORK}" --format '{{.Internal}}')"
[[ "${app_internal}" == false ]] || fail "${APP_NETWORK} must remain non-internal for validated localhost publication"
[[ "${db_internal}" == true ]] || fail "${DB_NETWORK} must be internal"

app_networks="$(docker inspect "${app_id}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"
db_networks="$(docker inspect "${db_id}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"
grep -qw "${APP_NETWORK}" <<<"${app_networks}" || fail "DVWA is missing ${APP_NETWORK}"
grep -qw "${DB_NETWORK}" <<<"${app_networks}" || fail "DVWA is missing ${DB_NETWORK}"
grep -qw "${DB_NETWORK}" <<<"${db_networks}" || fail "MariaDB is missing ${DB_NETWORK}"
if grep -qw "${APP_NETWORK}" <<<"${db_networks}"; then
  fail "MariaDB must not join ${APP_NETWORK}"
fi

if docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
  kali_networks="$(docker inspect "${KALI_CONTAINER}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"
  if grep -qw "${APP_NETWORK}" <<<"${kali_networks}"; then
    fail "Kali must be disconnected during smoke validation"
  fi
fi

cat > "${EVIDENCE_DIR}/smoke-summary.txt" <<EOF
result=PASS
http_status=${http_code}
host_mapping=${mapping}
app_health=${app_health}
db_health=${db_health}
app_network_internal=${app_internal}
db_network_internal=${db_internal}
db_host_bindings=${db_bindings}
kali_connected=false
EOF

echo "[smoke] PASS: HTTP ${http_code}, ${mapping}, pinned images, isolated database, Kali disconnected"
