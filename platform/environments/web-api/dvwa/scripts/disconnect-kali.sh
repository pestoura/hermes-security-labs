#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="dvwa"
KALI_CONTAINER="hermes-kali-mcp"
NETWORKS=(dvwa-lab dvwa-db)

if ! docker inspect "${KALI_CONTAINER}" >/dev/null 2>&1; then
  echo "[disconnect-kali] Kali container absent; nothing to do"
  exit 0
fi

for network in "${NETWORKS[@]}"; do
  if ! docker network inspect "${network}" >/dev/null 2>&1; then
    echo "[disconnect-kali] ${network} absent"
    continue
  fi

  project_label="$(docker network inspect "${network}" --format '{{index .Labels "com.docker.compose.project"}}')"
  if [[ "${project_label}" != "${PROJECT_NAME}" ]]; then
    echo "[disconnect-kali] ERROR: refusing foreign network ${network}" >&2
    exit 1
  fi

  endpoints="$(docker network inspect "${network}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
  if grep -Fxq "${KALI_CONTAINER}" <<<"${endpoints}"; then
    echo "[disconnect-kali] Disconnecting ${KALI_CONTAINER} from ${network}..."
    docker network disconnect "${network}" "${KALI_CONTAINER}"
  else
    echo "[disconnect-kali] ${KALI_CONTAINER} already disconnected from ${network}"
  fi

done

for network in "${NETWORKS[@]}"; do
  if docker network inspect "${network}" >/dev/null 2>&1; then
    endpoints="$(docker network inspect "${network}" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')"
    if grep -Fxq "${KALI_CONTAINER}" <<<"${endpoints}"; then
      echo "[disconnect-kali] ERROR: Kali remains connected to ${network}" >&2
      exit 1
    fi
  fi
done

echo "[disconnect-kali] KALI_DISCONNECTED=true"
