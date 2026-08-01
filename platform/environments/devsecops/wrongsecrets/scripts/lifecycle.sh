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
KALI_CONTAINER="hermes-kali-mcp"
DEFAULT_HOST_PORT="8082"
TARGET_IMAGE="docker.io/jeroenwillemsen/wrongsecrets:1.13.5-no-vault@sha256:a8abfafd1f10880ad6193af5c73341c3d721be31c71f812768b9300c47edc249"
PROXY_IMAGE="docker.io/alpine/socat@sha256:7955a82d66fd43c711946ba5c499e3ec8bf494db8ce6b32ad4df5e1b13b8f1d2"
COMPOSE=(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE")

export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export WRONGSECRETS_HOST_PORT="${WRONGSECRETS_HOST_PORT:-$DEFAULT_HOST_PORT}"

container_id() {
  "${COMPOSE[@]}" ps -q "$1" 2>/dev/null
}

network_exists() {
  docker network inspect "$1" >/dev/null 2>&1
}

assert_project_network() {
  local network_name="$1"
  network_exists "$network_name" || {
    echo "Network $network_name missing"
    return 1
  }
  docker network inspect "$network_name" \
    --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null |
    grep -qx "$PROJECT_NAME" || {
      echo "Network $network_name does not belong to project $PROJECT_NAME"
      return 1
    }
}

is_kali_running() {
  docker inspect "$KALI_CONTAINER" --format '{{.State.Status}}' 2>/dev/null |
    grep -qx running
}

is_kali_connected() {
  network_exists "$INTERNAL_NETWORK" || return 1
  docker network inspect "$INTERNAL_NETWORK" \
    --format '{{range $id, $container := .Containers}}{{$container.Name}} {{end}}' 2>/dev/null |
    grep -qw "$KALI_CONTAINER"
}

wait_for_service_health() {
  local service="$1"
  local attempts="${2:-30}"
  local delay="${3:-2}"
  local id status health
  for _ in $(seq 1 "$attempts"); do
    id="$(container_id "$service")"
    if [ -n "$id" ]; then
      status="$(docker inspect "$id" --format '{{.State.Status}}')"
      health="$(docker inspect "$id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
      [ "$status" = running ] && [ "$health" = healthy ] && return 0
      [ "$status" = exited ] && break
    fi
    sleep "$delay"
  done
  "${COMPOSE[@]}" logs --tail 100 "$service" || true
  return 1
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
  docker network disconnect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  if is_kali_connected; then
    echo "Kali disconnect failed"
    return 1
  fi
  echo "Kali disconnected from $INTERNAL_NETWORK"
}

assert_existing_networks_owned() {
  local network_name
  for network_name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$network_name"; then
      assert_project_network "$network_name"
    fi
  done
}

cleanup_project_resources() {
  assert_existing_networks_owned
  disconnect_kali
  "${COMPOSE[@]}" down --volumes --remove-orphans
  local network_name
  for network_name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$network_name"; then
      assert_project_network "$network_name"
      docker network rm "$network_name"
    fi
    ! network_exists "$network_name" || {
      echo "Network $network_name still present"
      return 1
    }
  done
}

start() {
  [ "$WRONGSECRETS_HOST_PORT" = "$DEFAULT_HOST_PORT" ] || {
    echo "WRONGSECRETS_HOST_PORT override is not allowed in this lifecycle"
    return 1
  }

  local proxy_id
  proxy_id="$(container_id "$PROXY_SERVICE")"
  if [ -z "$proxy_id" ] && nc -z 127.0.0.1 "$DEFAULT_HOST_PORT" 2>/dev/null; then
    echo "Port $DEFAULT_HOST_PORT is occupied by another process"
    return 1
  fi

  assert_existing_networks_owned
  "${COMPOSE[@]}" config --quiet
  "${COMPOSE[@]}" up -d --pull missing
  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  wait_for_service_health "$PRIMARY_SERVICE"
  wait_for_service_health "$PROXY_SERVICE"
  smoke
  echo "WrongSecrets started on 127.0.0.1:${WRONGSECRETS_HOST_PORT}"
}

status() {
  "${COMPOSE[@]}" ps
  local target_id proxy_id
  target_id="$(container_id "$PRIMARY_SERVICE")"
  proxy_id="$(container_id "$PROXY_SERVICE")"
  [ -n "$target_id" ] && docker inspect "$target_id" \
    --format 'target state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
  [ -n "$proxy_id" ] && docker inspect "$proxy_id" \
    --format 'proxy state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
  if is_kali_connected; then echo "Kali CONNECTED"; else echo "Kali NOT CONNECTED"; fi
}

smoke() {
  local target_id proxy_id target_networks proxy_networks mapping
  target_id="$(container_id "$PRIMARY_SERVICE")"
  proxy_id="$(container_id "$PROXY_SERVICE")"
  [ -n "$target_id" ] || { echo "Target container absent"; return 1; }
  [ -n "$proxy_id" ] || { echo "Proxy container absent"; return 1; }

  [ "$(docker inspect "$target_id" --format '{{.State.Status}}')" = running ]
  [ "$(docker inspect "$target_id" --format '{{.State.Health.Status}}')" = healthy ]
  [ "$(docker inspect "$proxy_id" --format '{{.State.Status}}')" = running ]
  [ "$(docker inspect "$proxy_id" --format '{{.State.Health.Status}}')" = healthy ]
  [ "$(docker inspect "$target_id" --format '{{.Config.Image}}')" = "$TARGET_IMAGE" ]
  [ "$(docker inspect "$proxy_id" --format '{{.Config.Image}}')" = "$PROXY_IMAGE" ]

  target_networks="$(docker inspect "$target_id" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' | xargs)"
  [ "$target_networks" = "$INTERNAL_NETWORK" ] || {
    echo "Unexpected target networks: $target_networks"
    return 1
  }
  proxy_networks="$(docker inspect "$proxy_id" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' | tr ' ' '\n' | sed '/^$/d' | sort | xargs)"
  [ "$proxy_networks" = "$INTERNAL_NETWORK $PUBLICATION_NETWORK" ] || {
    echo "Unexpected proxy networks: $proxy_networks"
    return 1
  }

  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  [ "$(docker network inspect "$INTERNAL_NETWORK" --format '{{.Internal}}')" = true ]
  [ "$(docker network inspect "$PUBLICATION_NETWORK" --format '{{.Internal}}')" = false ]

  mapping="$("${COMPOSE[@]}" port "$PROXY_SERVICE" 8080)"
  [ "$mapping" = "127.0.0.1:${DEFAULT_HOST_PORT}" ] || {
    echo "Unexpected host mapping: $mapping"
    return 1
  }
  [ "$(docker inspect "$target_id" --format '{{json .NetworkSettings.Ports}}')" = "{}" ] || {
    echo "Target unexpectedly publishes a port"
    return 1
  }
  ! is_kali_connected || {
    echo "Kali must be disconnected during smoke"
    return 1
  }
  curl -fsS "http://127.0.0.1:${DEFAULT_HOST_PORT}/actuator/health" >/dev/null
  if docker exec "$target_id" sh -c 'curl -fsS --connect-timeout 3 https://example.com >/dev/null 2>&1'; then
    echo "Target external HTTP egress unexpectedly succeeded"
    return 1
  fi
  echo "Smoke passed: localhost=${mapping} target-egress=denied"
}

connect_kali() {
  assert_project_network "$INTERNAL_NETWORK"
  is_kali_running || {
    echo "Kali container $KALI_CONTAINER is not running"
    return 1
  }
  local target_id
  target_id="$(container_id "$PRIMARY_SERVICE")"
  [ -n "$target_id" ] && [ "$(docker inspect "$target_id" --format '{{.State.Status}}')" = running ] || {
    echo "WrongSecrets target is not running"
    return 1
  }
  if is_kali_connected; then
    echo "Kali already connected to $INTERNAL_NETWORK"
    return 0
  fi
  docker network connect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  is_kali_connected || {
    echo "Kali connection failed"
    return 1
  }
  echo "Kali connected to $INTERNAL_NETWORK"
}

stop() {
  disconnect_kali
  "${COMPOSE[@]}" stop
  echo "WrongSecrets stopped"
}

reset() {
  cleanup_project_resources
  start
  echo "WrongSecrets reset complete"
}

destroy() {
  cleanup_project_resources
  ! "${COMPOSE[@]}" ps -aq | grep -q . || {
    echo "WrongSecrets containers still present"
    return 1
  }
  ! network_exists "$INTERNAL_NETWORK"
  ! network_exists "$PUBLICATION_NETWORK"
  echo "WrongSecrets destroyed"
}

case "${1:-}" in
  start) start ;;
  status) status ;;
  smoke) smoke ;;
  connect-kali) connect_kali ;;
  disconnect-kali) disconnect_kali ;;
  stop) stop ;;
  reset) reset ;;
  destroy) destroy ;;
  *) echo "Usage: $0 {start|status|smoke|connect-kali|disconnect-kali|stop|reset|destroy}"; exit 2 ;;
esac
