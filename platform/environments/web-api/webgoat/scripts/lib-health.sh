#!/usr/bin/env bash
# Sourced fragment: bounded, fail-closed Docker Compose health gate shared by
# start.sh and reset.sh so both lifecycle entrypoints enforce the SAME
# two-service readiness invariant (application service + publication service).
#
# It is sourced, never executed. Callers must export/define PROJECT_NAME and
# COMPOSE_FILE before calling. No target interaction, no offensive behaviour:
# the only commands used are `docker compose ps -q` and `docker inspect`.

# wait_for_services_healthy <label> <timeout_seconds> <service> [service...]
#
# Returns 0 only when every named service has a container whose health status
# is exactly "healthy". Fails closed (non-zero) on:
#   - no services requested
#   - a non-positive/malformed timeout
#   - any service reporting "unhealthy"
#   - the bounded timeout elapsing while any service is missing, starting,
#     or without a health status
wait_for_services_healthy() {
  local label="$1"
  local timeout="$2"
  shift 2 || return 1

  if [ "$#" -lt 1 ]; then
    echo "[${label}] No services requested for the health gate"
    return 1
  fi

  case "${timeout}" in
    '' | *[!0-9]*)
      echo "[${label}] Invalid health timeout: ${timeout}"
      return 1
      ;;
  esac
  if [ "${timeout}" -le 0 ]; then
    echo "[${label}] Invalid health timeout: ${timeout}"
    return 1
  fi

  local services=("$@")
  local interval="${HEALTH_POLL_INTERVAL:-5}"
  local deadline=$((SECONDS + timeout))
  local svc cid health pending

  while true; do
    pending=""
    for svc in "${services[@]}"; do
      cid="$(
        docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps -q "${svc}" 2>/dev/null || true
      )"
      if [ -z "${cid}" ]; then
        pending="${pending} ${svc}=missing"
        continue
      fi
      health="$(docker inspect -f "{{.State.Health.Status}}" "${cid}" 2>/dev/null || echo "none")"
      [ -n "${health}" ] || health="none"
      case "${health}" in
        healthy)
          ;;
        unhealthy)
          echo "[${label}] Service ${svc} reported unhealthy"
          return 1
          ;;
        *)
          pending="${pending} ${svc}=${health}"
          ;;
      esac
    done

    if [ -z "${pending}" ]; then
      return 0
    fi

    if [ "${SECONDS}" -ge "${deadline}" ]; then
      echo "[${label}] Timeout after ${timeout}s waiting for healthy:${pending}"
      return 1
    fi

    sleep "${interval}"
  done
}
