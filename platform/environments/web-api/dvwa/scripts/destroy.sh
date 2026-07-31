#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"
PROJECT_NAME="dvwa"
KALI_CONTAINER="hermes-kali-mcp"
NETWORKS=(dvwa-lab dvwa-db)
VOLUME_NAME="dvwa_dvwa-db-data"
DVWA_IMAGE="ghcr.io/digininja/dvwa:d45ba3c@sha256:091498cedec31b4a3091a1262e6a5a0ce5ec32d4bd26486558818346ccc89d67"
DB_IMAGE="docker.io/library/mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

fail() {
  echo "[destroy] ERROR: $*" >&2
  exit 1
}

verify_owned_resources() {
  local network project_label
  for network in "${NETWORKS[@]}"; do
    if docker network inspect "${network}" >/dev/null 2>&1; then
      project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
      [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing foreign network ${network}"
    fi
  done

  if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
    project_label="$(docker volume inspect "${VOLUME_NAME}" --format '{{index .Labels "com.docker.compose.project"}}')"
    [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing foreign volume ${VOLUME_NAME}"
  fi
}

cleanup_kali() {
  local network project_label endpoints
  if ! docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
    return 0
  fi

  for network in "${NETWORKS[@]}"; do
    if ! docker network inspect "${network}" >/dev/null 2>&1; then
      continue
    fi

    project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
    [[ "${project_label}" == "${PROJECT_NAME}" ]] || continue

    endpoints="$(docker network inspect "${network}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
    if grep -Fxq "${KALI_CONTAINER}" <<<"${endpoints}"; then
      docker network disconnect "${network}" "${KALI_CONTAINER}" >/dev/null
    fi
  done
}

verify_owned_resources
trap cleanup_kali EXIT
cleanup_kali

container_ids=()
while IFS= read -r id; do
  [[ -n "${id}" ]] && container_ids+=("${id}")
done < <("${COMPOSE[@]}" ps -aq 2>/dev/null || true)

echo "[destroy] Removing owned containers, volume, and networks..."
"${COMPOSE[@]}" down --volumes --remove-orphans

for id in "${container_ids[@]}"; do
  if docker container inspect "${id}" >/dev/null 2>&1; then
    fail "container ${id} remains"
  fi
done

if "${COMPOSE[@]}" ps -aq 2>/dev/null | grep -q .; then
  fail "Compose containers remain"
fi

for network in "${NETWORKS[@]}"; do
  if docker network inspect "${network}" >/dev/null 2>&1; then
    endpoints="$(docker network inspect "${network}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
    [[ -z "${endpoints}" ]] || fail "network ${network} still has endpoints: ${endpoints//$'\n'/ }"

    project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
    [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing residual foreign network ${network}"
    docker network rm "${network}" >/dev/null
  fi

done

if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  project_label="$(docker volume inspect "${VOLUME_NAME}" --format '{{index .Labels "com.docker.compose.project"}}')"
  [[ "${project_label}" == "${PROJECT_NAME}" ]] || fail "refusing residual foreign volume ${VOLUME_NAME}"
  docker volume rm "${VOLUME_NAME}" >/dev/null
fi

for network in "${NETWORKS[@]}"; do
  if docker network inspect "${network}" >/dev/null 2>&1; then
    fail "network ${network} remains"
  fi
done

if docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  fail "volume ${VOLUME_NAME} remains"
fi

if docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
  kali_state="$(docker inspect "${KALI_CONTAINER}" --format '{{.State.Status}}')"
  [[ "${kali_state}" == running ]] || fail "Kali is not running after destroy"
  kali_networks="$(docker inspect "${KALI_CONTAINER}" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"
  for network in "${NETWORKS[@]}"; do
    if grep -qw "${network}" <<<"${kali_networks}"; then
      fail "Kali remains connected to ${network}"
    fi
  done
fi

for image in "${DVWA_IMAGE}" "${DB_IMAGE}"; do
  if docker image inspect "${image}" >/dev/null 2>&1; then
    echo "[destroy] Image preserved: ${image}"
  fi
done

trap - EXIT
echo "[destroy] PASS: containers, volume, and networks absent; Kali disconnected"
