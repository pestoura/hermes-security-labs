#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=kali-mcp/scripts/env.sh
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${PROJECT_DIR}/data/results"
REPORT="${RESULTS_DIR}/healthcheck-$(date +%Y%m%dT%H%M%SZ).txt"
mkdir -p "${RESULTS_DIR}"

MAIN_CONTAINER="hermes-kali-mcp"
MAINT_CONTAINER="kali-maintenance"
LAB_NETWORK="hermes-kali-lab"
EGRESS_NETWORK="hermes-kali-egress"

main_state="$(docker inspect -f '{{.State.Status}}' "${MAIN_CONTAINER}" 2>/dev/null || echo missing)"
main_running=false
[ "${main_state}" = "running" ] && main_running=true

maint_state="$(docker inspect -f '{{.State.Status}}' "${MAINT_CONTAINER}" 2>/dev/null || echo missing)"
maint_running=false
[ "${maint_state}" != "missing" ] && maint_running=true

port_5000="$(docker ps --filter publish=5000 --format '{{.Names}}' || true)"
main_in_egress="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' "${MAIN_CONTAINER}" 2>/dev/null | grep -F "$(docker network inspect -f '{{.Id}}' "${EGRESS_NETWORK}" 2>/dev/null || true)" || true)"

mcp_bridge_test="skipped"
if [ "${main_running}" = "true" ]; then
  docker exec -i "${MAIN_CONTAINER}" mcp-server --help >/dev/null 2>&1 && mcp_bridge_test="pass" || mcp_bridge_test="fail"
fi

{
  echo "timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "main_container=${MAIN_CONTAINER}"
  echo "main_state=${main_state}"
  echo "main_running=${main_running}"
  echo "maintenance_container=${MAINT_CONTAINER}"
  echo "maintenance_state=${maint_state}"
  echo "maintenance_running=${maint_running}"
  echo "port_5000_published=$( [ -n "${port_5000}" ] && echo true || echo false )"
  echo "main_in_egress_network=$( [ -n "${main_in_egress}" ] && echo true || echo false )"
  echo "lab_internal=$(docker network inspect -f '{{.Internal}}' "${LAB_NETWORK}" 2>/dev/null || echo unknown)"
  echo "mcp_bridge_test=${mcp_bridge_test}"
} > "${REPORT}"

cat "${REPORT}"
