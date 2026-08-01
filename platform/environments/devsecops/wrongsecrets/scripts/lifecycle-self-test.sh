#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
LIFECYCLE="$SCRIPT_DIR/lifecycle.sh"
COMPOSE_FILE="$SCRIPT_DIR/../compose.yaml"

# shellcheck source=platform/environments/devsecops/wrongsecrets/scripts/lifecycle.sh
source "$LIFECYCLE"

self_test_compose_health_model() {
  python3 - "$COMPOSE_FILE" <<'PY'
import sys
import yaml

compose = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
services = compose["services"]
expected = ["CMD-SHELL", "kill -0 1"]
for name in ("wrongsecrets", "wrongsecrets-proxy"):
    actual = services[name]["healthcheck"]["test"]
    if actual != expected:
        raise SystemExit(f"unexpected healthcheck for {name}: {actual!r}")
    joined = " ".join(actual).lower()
    if "curl" in joined or "wget" in joined:
        raise SystemExit(f"network client must not be used for {name} liveness")
condition = services["wrongsecrets-proxy"]["depends_on"]["wrongsecrets"]["condition"]
if condition != "service_healthy":
    raise SystemExit(f"unexpected dependency condition: {condition}")
print("WRONGSECRETS_COMPOSE_HEALTH_MODEL_OK")
PY
}

self_test_http_readiness_recovers() (
  local counter
  counter="$(mktemp)"
  echo 0 > "$counter"
  HTTP_READY_TIMEOUT=3
  HTTP_READY_POLL_INTERVAL=1
  http_probe() {
    local n
    n="$(cat "$counter")"
    n=$((n + 1))
    echo "$n" > "$counter"
    [ "$n" -eq 3 ]
  }
  sleep_for() { :; }
  compose_command() { :; }
  wait_for_http_ready
  [ "$(cat "$counter")" -eq 3 ]
  rm -f "$counter"
)

self_test_http_readiness_times_out() (
  local counter
  counter="$(mktemp)"
  echo 0 > "$counter"
  HTTP_READY_TIMEOUT=3
  HTTP_READY_POLL_INTERVAL=1
  http_probe() {
    local n
    n="$(cat "$counter")"
    echo $((n + 1)) > "$counter"
    return 1
  }
  sleep_for() { :; }
  compose_command() { :; }
  if wait_for_http_ready; then
    echo "HTTP readiness unexpectedly succeeded" >&2
    exit 1
  fi
  [ "$(cat "$counter")" -eq 3 ]
  rm -f "$counter"
)

self_test_health_poll_tolerates_replacement() (
  local counter
  counter="$(mktemp)"
  echo 0 > "$counter"
  HEALTH_TIMEOUT=3
  HEALTH_POLL_INTERVAL=1
  service_container_ids() {
    local n
    n="$(cat "$counter")"
    n=$((n + 1))
    echo "$n" > "$counter"
    if [ "$n" -eq 1 ]; then echo old-id; else echo replacement-id; fi
  }
  inspect_container_state() {
    [ "$1" = old-id ] && return 1
    echo 'running|healthy'
  }
  sleep_for() { :; }
  compose_command() { :; }
  wait_for_service_health wrongsecrets
  [ "$(cat "$counter")" -eq 2 ]
  rm -f "$counter"
)

self_test_cleanup_waits_for_absence() (
  local counter
  counter="$(mktemp)"
  echo 0 > "$counter"
  ABSENCE_TIMEOUT=3
  ABSENCE_POLL_INTERVAL=1
  project_container_ids() {
    local n
    n="$(cat "$counter")"
    n=$((n + 1))
    echo "$n" > "$counter"
    [ "$n" -lt 3 ] && echo owned-container
  }
  sleep_for() { :; }
  wait_project_containers_absent
  [ "$(cat "$counter")" -eq 3 ]
  rm -f "$counter"
)

self_test_egress_proof_is_topology_based() {
  grep -Fq 'target-egress=denied-by-internal-network' "$LIFECYCLE"
  if grep -Fq 'Target external HTTP egress unexpectedly succeeded' "$LIFECYCLE"; then
    echo "obsolete target curl egress probe remains" >&2
    return 1
  fi
  if grep -Fq 'docker_command exec "$target_id"' "$LIFECYCLE"; then
    echo "target egress proof must not depend on an unavailable in-container client" >&2
    return 1
  fi
}

self_test_compose_health_model
self_test_http_readiness_recovers
self_test_http_readiness_times_out
self_test_health_poll_tolerates_replacement
self_test_cleanup_waits_for_absence
self_test_egress_proof_is_topology_based

echo "WRONGSECRETS_LIFECYCLE_SELF_TEST_OK"
