#!/usr/bin/env bash
set -euo pipefail

ENV_ID="${1:-}"
ACTION="${2:-}"
if [ -z "$ENV_ID" ] || [ -z "$ACTION" ]; then
  echo "Usage: $0 <environment-id> {config|start|status|smoke|connect-kali|disconnect-kali|stop|reset|destroy}" >&2
  exit 2
fi

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/../.." && pwd)"
CATALOG="$REPO_ROOT/platform/phase2/environments.yaml"
GENERATOR="$REPO_ROOT/platform/scripts/phase2_compose.py"
RUNTIME_DIR="$REPO_ROOT/.runtime/phase2/$ENV_ID"
COMPOSE_FILE="$RUNTIME_DIR/compose.yaml"
PROJECT_NAME="$ENV_ID"
TARGET_SERVICE="target"
PROXY_SERVICE="proxy"
INTERNAL_NETWORK="${ENV_ID}-internal"
PUBLICATION_NETWORK="${ENV_ID}-publication"
KALI_CONTAINER="${HERMES_KALI_CONTAINER:-hermes-kali-mcp}"
HOST_PORT="$(python3 - "$CATALOG" "$ENV_ID" <<'PY'
import sys, yaml
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
matches = [x for x in data["environments"] if x["id"] == sys.argv[2]]
if len(matches) != 1:
    raise SystemExit(f"expected one catalog item, found {len(matches)}")
print(matches[0]["host_port"])
PY
)"
python3 "$GENERATOR" "$ENV_ID" --output "$COMPOSE_FILE"
COMPOSE=(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE")

container_id() {
  "${COMPOSE[@]}" ps -q "$1" 2>/dev/null
}

network_exists() {
  docker network inspect "$1" >/dev/null 2>&1
}

assert_project_network() {
  local network_name="$1"
  network_exists "$network_name" || {
    echo "Network $network_name missing" >&2
    return 1
  }
  docker network inspect "$network_name" \
    --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null |
    grep -qx "$PROJECT_NAME" || {
      echo "Network $network_name is not owned by Compose project $PROJECT_NAME" >&2
      return 1
    }
}

is_kali_running() {
  docker inspect "$KALI_CONTAINER" --format '{{.State.Status}}' 2>/dev/null | grep -qx running
}

is_kali_connected() {
  network_exists "$INTERNAL_NETWORK" || return 1
  docker network inspect "$INTERNAL_NETWORK" \
    --format '{{range $id, $container := .Containers}}{{$container.Name}} {{end}}' 2>/dev/null |
    grep -qw "$KALI_CONTAINER"
}

disconnect_kali() {
  if ! network_exists "$INTERNAL_NETWORK"; then
    echo "Kali already disconnected: lab network absent"
    return 0
  fi
  assert_project_network "$INTERNAL_NETWORK"
  if ! is_kali_connected; then
    echo "Kali already disconnected from $INTERNAL_NETWORK"
    return 0
  fi
  docker network disconnect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  ! is_kali_connected || {
    echo "Kali disconnect failed" >&2
    return 1
  }
  echo "Kali disconnected from $INTERNAL_NETWORK"
}

assert_existing_networks_owned() {
  local name
  for name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$name"; then
      assert_project_network "$name"
    fi
  done
}

wait_healthy() {
  local service="$1" id status health
  for _ in $(seq 1 60); do
    id="$(container_id "$service")"
    if [ -n "$id" ]; then
      status="$(docker inspect "$id" --format '{{.State.Status}}')"
      health="$(docker inspect "$id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
      [ "$status" = running ] && [ "$health" = healthy ] && return 0
      [ "$status" = exited ] && break
    fi
    sleep 2
  done
  "${COMPOSE[@]}" logs --tail 100 "$service" || true
  return 1
}

cleanup() {
  assert_existing_networks_owned
  disconnect_kali
  "${COMPOSE[@]}" down --volumes --remove-orphans
  local name
  for name in "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK"; do
    if network_exists "$name"; then
      assert_project_network "$name"
      docker network rm "$name"
    fi
    ! network_exists "$name" || {
      echo "Network $name still present" >&2
      return 1
    }
  done
}

config() {
  "${COMPOSE[@]}" config --quiet
  "${COMPOSE[@]}" config
}

smoke() {
  local target_id proxy_id target_networks proxy_networks mapping expected_networks
  target_id="$(container_id "$TARGET_SERVICE")"
  proxy_id="$(container_id "$PROXY_SERVICE")"
  [ -n "$target_id" ] || { echo "Target container absent" >&2; return 1; }
  [ -n "$proxy_id" ] || { echo "Proxy container absent" >&2; return 1; }

  [ "$(docker inspect "$target_id" --format '{{.State.Status}}')" = running ]
  [ "$(docker inspect "$target_id" --format '{{.State.Health.Status}}')" = healthy ]
  [ "$(docker inspect "$proxy_id" --format '{{.State.Status}}')" = running ]
  [ "$(docker inspect "$proxy_id" --format '{{.State.Health.Status}}')" = healthy ]
  docker inspect "$target_id" --format '{{.Config.Image}}' | grep -q "^hermes-local/${ENV_ID}:"
  [ "$(docker inspect "$proxy_id" --format '{{.Config.Image}}')" = "docker.io/alpine/socat@sha256:7955a82d66fd43c711946ba5c499e3ec8bf494db8ce6b32ad4df5e1b13b8f1d2" ]

  target_networks="$(docker inspect "$target_id" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' | xargs)"
  [ "$target_networks" = "$INTERNAL_NETWORK" ] || {
    echo "Unexpected target networks: $target_networks" >&2
    return 1
  }
  proxy_networks="$(docker inspect "$proxy_id" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' | tr ' ' '\n' | sed '/^$/d' | sort | xargs)"
  expected_networks="$(printf '%s\n%s\n' "$INTERNAL_NETWORK" "$PUBLICATION_NETWORK" | sort | xargs)"
  [ "$proxy_networks" = "$expected_networks" ] || {
    echo "Unexpected proxy networks: $proxy_networks" >&2
    return 1
  }

  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  [ "$(docker network inspect "$INTERNAL_NETWORK" --format '{{.Internal}}')" = true ]
  [ "$(docker network inspect "$PUBLICATION_NETWORK" --format '{{.Internal}}')" = false ]

  mapping="$("${COMPOSE[@]}" port "$PROXY_SERVICE" 8080)"
  [ "$mapping" = "127.0.0.1:${HOST_PORT}" ] || {
    echo "Unexpected localhost mapping: $mapping" >&2
    return 1
  }
  [ "$(docker inspect "$target_id" --format '{{json .NetworkSettings.Ports}}')" = "{}" ] || {
    echo "Target unexpectedly publishes a host port" >&2
    return 1
  }
  ! is_kali_connected || {
    echo "Kali must be disconnected during smoke" >&2
    return 1
  }

  curl -fsS "http://127.0.0.1:${HOST_PORT}/health" >/dev/null
  curl -fsS "http://127.0.0.1:${HOST_PORT}/api/meta" >/dev/null

  if docker exec "$target_id" python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=3).read(1)" >/dev/null 2>&1; then
    echo "Target external egress unexpectedly succeeded" >&2
    return 1
  fi
  echo "Smoke passed: env=$ENV_ID localhost=$mapping target-egress=denied"
}

start() {
  local proxy_id
  proxy_id="$(container_id "$PROXY_SERVICE")"
  if [ -z "$proxy_id" ] && nc -z 127.0.0.1 "$HOST_PORT" 2>/dev/null; then
    echo "Port $HOST_PORT is occupied by another process" >&2
    return 1
  fi
  assert_existing_networks_owned
  "${COMPOSE[@]}" config --quiet
  "${COMPOSE[@]}" up -d --build --pull missing
  assert_project_network "$INTERNAL_NETWORK"
  assert_project_network "$PUBLICATION_NETWORK"
  wait_healthy "$TARGET_SERVICE"
  wait_healthy "$PROXY_SERVICE"
  smoke
}

status() {
  "${COMPOSE[@]}" ps
  local target_id proxy_id
  target_id="$(container_id "$TARGET_SERVICE")"
  proxy_id="$(container_id "$PROXY_SERVICE")"
  [ -z "$target_id" ] || docker inspect "$target_id" \
    --format 'target state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
  [ -z "$proxy_id" ] || docker inspect "$proxy_id" \
    --format 'proxy state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} image={{.Config.Image}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
  if is_kali_connected; then echo "Kali CONNECTED"; else echo "Kali NOT CONNECTED"; fi
}

connect_kali() {
  assert_project_network "$INTERNAL_NETWORK"
  is_kali_running || {
    echo "Kali container $KALI_CONTAINER is not running" >&2
    return 1
  }
  local target_id
  target_id="$(container_id "$TARGET_SERVICE")"
  [ -n "$target_id" ] && [ "$(docker inspect "$target_id" --format '{{.State.Status}}')" = running ] || {
    echo "Target is not running" >&2
    return 1
  }
  if is_kali_connected; then
    echo "Kali already connected to $INTERNAL_NETWORK"
    return 0
  fi
  docker network connect "$INTERNAL_NETWORK" "$KALI_CONTAINER"
  is_kali_connected || { echo "Kali connection failed" >&2; return 1; }
  echo "Kali connected to $INTERNAL_NETWORK"
}

stop() {
  disconnect_kali
  "${COMPOSE[@]}" stop
}

reset() {
  cleanup
  start
}

destroy() {
  cleanup
  ! "${COMPOSE[@]}" ps -aq | grep -q . || {
    echo "Lab containers still present" >&2
    return 1
  }
  ! network_exists "$INTERNAL_NETWORK"
  ! network_exists "$PUBLICATION_NETWORK"
  echo "$ENV_ID destroyed"
}

case "$ACTION" in
  config) config ;;
  start) start ;;
  status) status ;;
  smoke) smoke ;;
  connect-kali) connect_kali ;;
  disconnect-kali) disconnect_kali ;;
  stop) stop ;;
  reset) reset ;;
  destroy) destroy ;;
  *) echo "Unsupported action: $ACTION" >&2; exit 2 ;;
esac
