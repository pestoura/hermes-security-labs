source "$(dirname "$0")/env.sh"
#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <operation>" >&2
  exit 2
fi

case "${1}" in
  rebuild-image|update-wordlists|update-nuclei-templates|verify-sources|status) ;;
  *) echo "Unsupported operation: ${1}" >&2; exit 2 ;;
esac

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/compose.yaml"
PROJECT="hermes-kali-mcp"
ALLOWED_SOURCES="${PROJECT_DIR}/config/maintenance-sources.txt"
MAIN_CONTAINER="${PROJECT}-mcp"
MAINT_CONTAINER="${PROJECT}-maintenance"
OP="${1}"

case "${OP}" in
  rebuild-image|verify-sources|status)
    if [ "${OP}" = "verify-sources" ]; then
      echo "Allowed maintenance sources:"
      grep -E '^https?://' "${ALLOWED_SOURCES}" || true
    fi
    echo "Compose ps:"
    docker compose -f "${COMPOSE_FILE}" -p "${PROJECT}" ps || true
    echo "Published ports:"
    docker ps --filter "name=${MAIN_CONTAINER}" --format '{{.Names}} {{.Ports}}' || true
    echo "Main container networks:"
    docker inspect -f '{{json .NetworkSettings.Networks}}' "${MAIN_CONTAINER}" 2>/dev/null || true
    ;;
  update-wordlists|update-nuclei-templates)
    echo "Running maintenance operation: ${OP}"
    docker compose -f "${COMPOSE_FILE}" -p "${PROJECT}" run --rm --profile maintenance kali-maintenance env MAINTENANCE_OP="${OP}" bash -lc '
      set -euo pipefail
      echo "Maintenance container started for: ${MAINTENANCE_OP}"
      echo "No-op maintenance task by design."
    '
    ;;
  *) echo "Unsupported operation: ${OP}" >&2; exit 2 ;;
esac

if docker ps --filter "name=^/${MAINT_CONTAINER}$" --format '{{.Names}}' | grep -q "${MAINT_CONTAINER}"; then
  echo "FAIL: maintenance container still running" >&2
  exit 1
fi

if docker inspect -f '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' "${MAIN_CONTAINER}" 2>/dev/null | grep -F "$(docker network inspect -f '{{.Id}}' "${PROJECT}-egress" 2>/dev/null || true)" >/dev/null 2>&1; then
  echo "FAIL: main container has egress network" >&2
  exit 1
fi

if [ -n "$(docker ps --filter publish=5000 --format '{{.Names}}' || true)" ]; then
  echo "FAIL: port 5000 is published" >&2
  exit 1
fi

if docker inspect -f '{{json .Mounts}}' "${MAIN_CONTAINER}" 2>/dev/null | grep -q 'docker.sock'; then
  echo "FAIL: Docker socket mounted" >&2
  exit 1
fi

echo "Maintenance operation ${OP} completed."
