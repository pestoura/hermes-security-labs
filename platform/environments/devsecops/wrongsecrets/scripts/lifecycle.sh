#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/../compose.yaml"
PROJECT_NAME="wrongsecrets"
PRIMARY_SERVICE="wrongsecrets"
PROXY_SERVICE="wrongsecrets-proxy"
INTERNAL_NETWORK="wrongsecrets-internal"
PUBLICATION_NETWORK="wrongsecrets-publication"
KALI_CONTAINER="${HERMES_KALI_CONTAINER:-hermes-kali-mcp}"
DEFAULT_HOST_PORT="8082"
TARGET_IMAGE="docker.io/jeroenwillemsen/wrongsecrets:1.13.5-no-vault@sha256:a8abfafd1f10880ad6193af5c73341c3d721be31c71f812768b9300c47edc249"
PROXY_IMAGE="docker.io/alpine/socat@sha256:7955a82d66fd43c711946ba5c499e3ec8bf494db8ce6b32ad4df5e1b13b8f1d2"
DOCKER_COMMAND_TIMEOUT="${WRONGSECRETS_DOCKER_COMMAND_TIMEOUT:-60}"
COMPOSE_UP_TIMEOUT="${WRONGSECRETS_COMPOSE_UP_TIMEOUT:-300}"
COMPOSE_DOWN_TIMEOUT="${WRONGSECRETS_COMPOSE_DOWN_TIMEOUT:-120}"
HEALTH_TIMEOUT="${WRONGSECRETS_HEALTH_TIMEOUT:-120}"
HEALTH_POLL_INTERVAL="${WRONGSECRETS_HEALTH_POLL_INTERVAL:-2}"
HTTP_READY_TIMEOUT="${WRONGSECRETS_HTTP_READY_TIMEOUT:-180}"
HTTP_READY_POLL_INTERVAL="${WRONGSECRETS_HTTP_READY_POLL_INTERVAL:-2}"
ABSENCE_TIMEOUT="${WRONGSECRETS_ABSENCE_TIMEOUT:-30}"
ABSENCE_POLL_INTERVAL="${WRONGSECRETS_ABSENCE_POLL_INTERVAL:-1}"
COMPOSE=(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE")

export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export WRONGSECRETS_HOST_PORT="${WRONGSECRETS_HOST_PORT:-$DEFAULT_HOST_PORT}"

validate_positive_integer() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || {
    echo "$name must be a positive integer, got: $value" >&2
    exit 2
  }
}

for timeout_setting in \
  DOCKER_COMMAND_TIMEOUT COMPOSE_UP_TIMEOUT COMPOSE_DOWN_TIMEOUT \
  HEALTH_TIMEOUT HEALTH_POLL_INTERVAL HTTP_READY_TIMEOUT \
  HTTP_READY_POLL_INTERVAL ABSENCE_TIMEOUT ABSENCE_POLL_INTERVAL; do
  validate_positive_integer "$timeout_setting" "${!timeout_setting}"
done

run_with_timeout() {
  local seconds="$1"
  shift
  timeout --foreground --signal=TERM --kill-after=10s "${seconds}s" "$@"
}

docker_command() {
  run_with_timeout "$DOCKER_COMMAND_TIMEOUT" docker "$@"
}

compose_command() {
  local seconds="$1"
  shift
  run_with_timeout "$seconds" "${COMPOSE[@]}" "$@"
}

sleep_for() {
  sleep "$1"
}

poll_count() {
  local timeout_seconds="$1" interval_seconds="$2"
  echo $(((timeout_seconds + interval_seconds - 1) / interval_seconds))
}

service_container_ids() {
  local service="$1"
  docker_command ps -aq \
    --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter "label=com.docker.compose.service=$service"
}

project_container_ids() {
  docker_command ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME"
}

project_volume_names() {
  docker_command volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME"
}

container_id() {
  local service="$1" ids
  ids="$(service_container_ids "$service")" || return 1
  printf '%s\n' "$ids" | sed '/^$/d' | head -n 1
}

inspect_container_value() {
  local id="$1" format="$2"
  docker_command inspect "$id" --format "$format" 2>/dev/null
}

inspect_container_state() {
  inspect_container_value "$1" '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
}

network_exists() {
  docker_command network inspect "$1" >/dev/null 2>&1
}

assert_project_network() {
  local network_name="$1" owner
  network_exists "$network_name" || {
    echo "Network $network_name missing" >&2
    return 1
  }
  owner="$(docker_command network inspect "$network_name" \
    --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null)" || {
      echo "Cannot inspect network $network_name" >&2
      return 1
    }
  [ "$owner" = "$PROJECT_NAME" ] || {
    echo "Network $network_name does not belong to project $PROJECT_NAME" >&2
    return 1
  }
}

assert_project_volume() {
  local volume_name="$1" owner
  owner="$(docker_command volume inspect "$volume_name" \
    --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null)" || {
      echo "Cannot inspect volume $volume_name" >&2
      return 1
    }
  [ "$owner" = "$PROJECT_NAME" ] || {
    echo "Volume $volume_name does not belong to project $PROJECT_NAME" >&2
    return 1
  }
}

assert_existing_networks_owned() {
  local network_name
  for network_name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$network_name"; then
      assert_project_network "$network_name"
    fi
  done
}

is_kali_running() {
  local state
  state="$(inspect_container_value "$KALI_CONTAINER" '{{.State.Status}}')" || return 1
  [ "$state" = running ]
}

is_kali_healthy() {
  local health
  health="$(inspect_container_value "$KALI_CONTAINER" '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')" || return 1
  [ "$health" = healthy ]
}

is_kali_connected() {
  network_exists "$INTERNAL_NETWORK" || return 1
  docker_command network inspect "$INTERNAL_NETWORK" \
    --format '{{range $id, $container := .Containers}}{{$container.Name}} {{end}}' 2>/dev/null |
    grep -qw "$KALI_CONTAINER"
}

disconnect_kali() {
  if ! network_exists "$INTERNAL_NETWORK"; then
    echo "Kali already disconnected: network absent"
    return 0
  fi
  assert_project_network "$INTERNAL_NETWORK"
  if ! is_kali_connected; then
    echo "Kali already disconnected from $INTERNAL_NETWORK"
    return 0
  fi
  docker_command network disconnect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  ! is_kali_connected || {
    echo "Kali disconnect failed" >&2
    return 1
  }
  echo "Kali disconnected from $INTERNAL_NETWORK"
}

wait_for_service_health() {
  local service="$1" polls ids id state status health
  polls="$(poll_count "$HEALTH_TIMEOUT" "$HEALTH_POLL_INTERVAL")"
  for _ in $(seq 1 "$polls"); do
    if ids="$(service_container_ids "$service" 2>/dev/null)"; then
      while IFS= read -r id; do
        [ -n "$id" ] || continue
        if state="$(inspect_container_state "$id")"; then
          status="${state%%|*}"
          health="${state#*|}"
          if [ "$status" = running ] && [ "$health" = healthy ]; then
            return 0
          fi
          [ "$status" = exited ] && break
        else
          echo "Transient container replacement observed: service=$service id=$id" >&2
        fi
      done <<< "$ids"
    fi
    sleep_for "$HEALTH_POLL_INTERVAL"
  done
  compose_command "$DOCKER_COMMAND_TIMEOUT" logs --tail 100 "$service" || true
  echo "Service did not become healthy within ${HEALTH_TIMEOUT}s: $service" >&2
  return 1
}

http_probe() {
  curl -fsS --max-time 5 \
    "http://127.0.0.1:${DEFAULT_HOST_PORT}/actuator/health" >/dev/null
}

wait_for_http_ready() {
  local polls
  polls="$(poll_count "$HTTP_READY_TIMEOUT" "$HTTP_READY_POLL_INTERVAL")"
  for _ in $(seq 1 "$polls"); do
    if http_probe; then
      return 0
    fi
    sleep_for "$HTTP_READY_POLL_INTERVAL"
  done
  compose_command "$DOCKER_COMMAND_TIMEOUT" logs --tail 100 "$PRIMARY_SERVICE" "$PROXY_SERVICE" || true
  echo "WrongSecrets HTTP endpoint did not become ready within ${HTTP_READY_TIMEOUT}s" >&2
  return 1
}

wait_project_containers_absent() {
  local polls ids
  polls="$(poll_count "$ABSENCE_TIMEOUT" "$ABSENCE_POLL_INTERVAL")"
  for _ in $(seq 1 "$polls"); do
    ids="$(project_container_ids 2>/dev/null)" || ids=""
    [ -z "$ids" ] && return 0
    sleep_for "$ABSENCE_POLL_INTERVAL"
  done
  echo "WrongSecrets containers remain after ${ABSENCE_TIMEOUT}s" >&2
  project_container_ids >&2 || true
  return 1
}

wait_project_volumes_absent() {
  local polls names
  polls="$(poll_count "$ABSENCE_TIMEOUT" "$ABSENCE_POLL_INTERVAL")"
  for _ in $(seq 1 "$polls"); do
    names="$(project_volume_names 2>/dev/null)" || names=""
    [ -z "$names" ] && return 0
    sleep_for "$ABSENCE_POLL_INTERVAL"
  done
  echo "WrongSecrets volumes remain after ${ABSENCE_TIMEOUT}s" >&2
  project_volume_names >&2 || true
  return 1
}

config() {
  compose_command "$DOCKER_COMMAND_TIMEOUT" config --quiet
  compose_command "$DOCKER_COMMAND_TIMEOUT" config
}

require_container_id() {
  local service="$1" id
  id="$(container_id "$service" 2>/dev/null)" || id=""
  [ -n "$id" ] || {
    echo "$service container absent" >&2
    return 1
  }
  printf '%s\n' "$id"
}

smoke() {
  local target_id proxy_id target_state proxy_state
  local target_networks proxy_networks expected_networks mapping ports

  target_id="$(require_container_id "$PRIMARY_SERVICE")" || return 1
  proxy_id="$(require_container_id "$PROXY_SERVICE")" || return 1
  target_state="$(inspect_container_state "$target_id")" || return 1
  proxy_state="$(inspect_container_state "$proxy_id")" || return 1
  [ "$target_state" = 'running|healthy' ] || {
    echo "Unexpected target state: $target_state" >&2
    return 1
  }
  [ "$proxy_state" = 'running|healthy' ] || {
    echo "Unexpected proxy state: $proxy_state" >&2
    return 1
  }

  [ "$(inspect_container_value "$target_id" '{{.Config.Image}}')" = "$TARGET_IMAGE" ]
  [ "$(inspect_container_value "$proxy_id" '{{.Config.Image}}')" = "$PROXY_IMAGE" ]

  target_networks="$(inspect_container_value "$target_id" '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')" || return 1
  target_networks="$(xargs <<< "$target_networks")"
  [ "$target_networks" = "$INTERNAL_NETWORK" ] || {
    echo "Unexpected target networks: $target_networks" >&2
    return 1
  }

  proxy_networks="$(inspect_container_value "$proxy_id" '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')" || return 1
  proxy_networks="$(tr ' ' '\n' <<< "$proxy_networks" | sed '/^$/d' | sort | xargs)"
  expected_networks="$(printf '%s\n%s\n' "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK" | sort | xargs)"
  [ "$proxy_networks" = "$expected_networks" ] || {
    echo "Unexpected proxy networks: $proxy_networks" >&2
    return 1
  }

  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  [ "$(docker_command network inspect "$INTERNAL_NETWORK" --format '{{.Internal}}')" = true ]
  [ "$(docker_command network inspect "$PUBLICATION_NETWORK" --format '{{.Internal}}')" = false ]

  mapping="$(compose_command "$DOCKER_COMMAND_TIMEOUT" port "$PROXY_SERVICE" 8080)"
  [ "$mapping" = "127.0.0.1:${DEFAULT_HOST_PORT}" ] || {
    echo "Unexpected host mapping: $mapping" >&2
    return 1
  }

  ports="$(inspect_container_value "$target_id" '{{json .NetworkSettings.Ports}}')" || return 1
  [ "$ports" = "{}" ] || {
    echo "Target unexpectedly publishes a host port" >&2
    return 1
  }

  ! is_kali_connected || {
    echo "Kali must be disconnected during smoke" >&2
    return 1
  }

  http_probe
  echo "Smoke passed: localhost=$mapping target-egress=denied-by-internal-network"
}

start() {
  local proxy_id
  [ "$WRONGSECRETS_HOST_PORT" = "$DEFAULT_HOST_PORT" ] || {
    echo "WRONGSECRETS_HOST_PORT override is not allowed in this lifecycle" >&2
    return 1
  }

  proxy_id="$(container_id "$PROXY_SERVICE" 2>/dev/null)" || proxy_id=""
  if [ -z "$proxy_id" ] && nc -z 127.0.0.1 "$DEFAULT_HOST_PORT" 2>/dev/null; then
    echo "Port $DEFAULT_HOST_PORT is occupied by another process" >&2
    return 1
  fi

  assert_existing_networks_owned
  compose_command "$DOCKER_COMMAND_TIMEOUT" config --quiet
  compose_command "$COMPOSE_UP_TIMEOUT" up -d --pull missing
  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  wait_for_service_health "$PRIMARY_SERVICE"
  wait_for_service_health "$PROXY_SERVICE"
  wait_for_http_ready
  smoke
  echo "WrongSecrets started on 127.0.0.1:${WRONGSECRETS_HOST_PORT}"
}

status() {
  local target_id proxy_id state
  compose_command "$DOCKER_COMMAND_TIMEOUT" ps
  target_id="$(container_id "$PRIMARY_SERVICE" 2>/dev/null)" || target_id=""
  proxy_id="$(container_id "$PROXY_SERVICE" 2>/dev/null)" || proxy_id=""

  if [ -n "$target_id" ] && state="$(inspect_container_value "$target_id" 'target state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"; then
    echo "$state"
  fi
  if [ -n "$proxy_id" ] && state="$(inspect_container_value "$proxy_id" 'proxy state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}')"; then
    echo "$state"
  fi
  if is_kali_connected; then echo "Kali CONNECTED"; else echo "Kali NOT CONNECTED"; fi
}

connect_kali() {
  local target_id state
  assert_project_network "$INTERNAL_NETWORK"
  is_kali_running || {
    echo "Kali container $KALI_CONTAINER is not running" >&2
    return 1
  }
  is_kali_healthy || {
    echo "Kali container $KALI_CONTAINER is not healthy" >&2
    return 1
  }

  target_id="$(container_id "$PRIMARY_SERVICE" 2>/dev/null)" || target_id=""
  [ -n "$target_id" ] || {
    echo "WrongSecrets target is absent" >&2
    return 1
  }
  state="$(inspect_container_state "$target_id")" || {
    echo "WrongSecrets target disappeared before Kali attachment" >&2
    return 1
  }
  [ "$state" = 'running|healthy' ] || {
    echo "WrongSecrets target is not healthy" >&2
    return 1
  }

  if is_kali_connected; then
    echo "Kali already connected to $INTERNAL_NETWORK"
    return 0
  fi
  docker_command network connect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  is_kali_connected || {
    echo "Kali connection failed" >&2
    return 1
  }
  echo "Kali connected to $INTERNAL_NETWORK"
}

stop() {
  disconnect_kali
  compose_command "$DOCKER_COMMAND_TIMEOUT" stop
  echo "WrongSecrets stopped"
}

remove_owned_project_volumes() {
  local names name
  names="$(project_volume_names 2>/dev/null)" || names=""
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    assert_project_volume "$name"
    docker_command volume rm "$name"
  done <<< "$names"
}

cleanup_project_resources() {
  local down_rc=0 network_name
  assert_existing_networks_owned
  disconnect_kali
  if compose_command "$COMPOSE_DOWN_TIMEOUT" down --volumes --remove-orphans; then
    down_rc=0
  else
    down_rc=$?
    echo "Compose down returned exit=$down_rc; verifying owned resources" >&2
  fi

  wait_project_containers_absent
  for network_name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$network_name"; then
      assert_project_network "$network_name"
      docker_command network rm "$network_name"
    fi
    ! network_exists "$network_name" || {
      echo "Network $network_name still present" >&2
      return 1
    }
  done

  remove_owned_project_volumes
  wait_project_volumes_absent
  if [ "$down_rc" -ne 0 ]; then
    echo "Cleanup accepted after non-zero compose down because all owned resources are absent" >&2
  fi
}

reset() {
  cleanup_project_resources
  start
  echo "WrongSecrets reset complete"
}

destroy() {
  cleanup_project_resources
  [ -z "$(project_container_ids 2>/dev/null || true)" ] || {
    echo "WrongSecrets containers still present" >&2
    return 1
  }
  [ -z "$(project_volume_names 2>/dev/null || true)" ] || {
    echo "WrongSecrets volumes still present" >&2
    return 1
  }
  ! network_exists "$INTERNAL_NETWORK"
  ! network_exists "$PUBLICATION_NETWORK"
  is_kali_running || {
    echo "Kali container $KALI_CONTAINER is not running" >&2
    return 1
  }
  is_kali_healthy || {
    echo "Kali container $KALI_CONTAINER is not healthy" >&2
    return 1
  }
  ! is_kali_connected || {
    echo "Kali remains connected to $INTERNAL_NETWORK" >&2
    return 1
  }
  echo "WrongSecrets destroyed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    config) config ;;
    start) start ;;
    status) status ;;
    smoke) smoke ;;
    connect-kali) connect_kali ;;
    disconnect-kali) disconnect_kali ;;
    stop) stop ;;
    reset) reset ;;
    destroy) destroy ;;
    *) echo "Usage: $0 {config|start|status|smoke|connect-kali|disconnect-kali|stop|reset|destroy}" >&2; exit 2 ;;
  esac
fi
