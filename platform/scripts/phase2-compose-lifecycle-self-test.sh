#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
LIFECYCLE="$ROOT/platform/scripts/phase2-compose-lab.sh"

set -- cicd-goat __self_test_library__
# shellcheck source=platform/scripts/phase2-compose-lab.sh
source "$LIFECYCLE"

self_test_wait_healthy_disappearing_id() (
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
    if [ "$n" -eq 1 ]; then echo old-id; else echo new-id; fi
  }
  inspect_container_state() {
    [ "$1" = old-id ] && return 1
    echo 'running|healthy'
  }
  compose_command() { :; }
  sleep_for() { :; }
  wait_healthy target
  [ "$(cat "$counter")" -ge 2 ]
  rm -f "$counter"
)

self_test_wait_healthy_replacement() (
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
    if [ "$n" -eq 1 ]; then echo first-id; else echo replacement-id; fi
  }
  inspect_container_state() {
    if [ "$1" = first-id ]; then echo 'running|starting'; else echo 'running|healthy'; fi
  }
  compose_command() { :; }
  sleep_for() { :; }
  wait_healthy proxy
  [ "$(cat "$counter")" -eq 2 ]
  rm -f "$counter"
)

self_test_wait_healthy_timeout() (
  local counter
  counter="$(mktemp)"
  echo 0 > "$counter"
  HEALTH_TIMEOUT=3
  HEALTH_POLL_INTERVAL=1
  service_container_ids() { echo static-id; }
  inspect_container_state() {
    local n
    n="$(cat "$counter")"
    echo $((n + 1)) > "$counter"
    echo 'running|starting'
  }
  compose_command() { :; }
  sleep_for() { :; }
  if wait_healthy proxy; then
    echo "wait_healthy unexpectedly succeeded" >&2
    exit 1
  fi
  [ "$(cat "$counter")" -eq 3 ]
  rm -f "$counter"
)

self_test_proxy_recovery_is_bounded() (
  local wait_counter compose_counter args_file
  wait_counter="$(mktemp)"
  compose_counter="$(mktemp)"
  args_file="$(mktemp)"
  echo 0 > "$wait_counter"
  echo 0 > "$compose_counter"
  wait_healthy() {
    local n
    n="$(cat "$wait_counter")"
    n=$((n + 1))
    echo "$n" > "$wait_counter"
    [ "$n" -eq 2 ]
  }
  service_is_healthy() { [ "$1" = "$TARGET_SERVICE" ]; }
  compose_command() {
    local n
    n="$(cat "$compose_counter")"
    echo $((n + 1)) > "$compose_counter"
    printf '%s\n' "$*" > "$args_file"
  }
  ensure_proxy_healthy
  [ "$(cat "$compose_counter")" -eq 1 ]
  grep -qx "$COMPOSE_UP_TIMEOUT up -d --no-deps --force-recreate $PROXY_SERVICE" "$args_file"
  [ "$(cat "$wait_counter")" -eq 2 ]
  rm -f "$wait_counter" "$compose_counter" "$args_file"
)

self_test_proxy_recovery_failure_is_bounded() (
  local wait_counter compose_counter
  wait_counter="$(mktemp)"
  compose_counter="$(mktemp)"
  echo 0 > "$wait_counter"
  echo 0 > "$compose_counter"
  wait_healthy() {
    local n
    n="$(cat "$wait_counter")"
    echo $((n + 1)) > "$wait_counter"
    return 1
  }
  service_is_healthy() { [ "$1" = "$TARGET_SERVICE" ]; }
  compose_command() {
    local n
    n="$(cat "$compose_counter")"
    echo $((n + 1)) > "$compose_counter"
  }
  if ensure_proxy_healthy; then
    echo "bounded proxy recovery unexpectedly succeeded" >&2
    exit 1
  fi
  [ "$(cat "$compose_counter")" -eq 1 ]
  [ "$(cat "$wait_counter")" -eq 2 ]
  rm -f "$wait_counter" "$compose_counter"
)

self_test_three_cycle_sequence() (
  local calls expected
  calls="$(mktemp)"
  : > "$calls"
  start() { echo start >> "$calls"; }
  smoke() { echo smoke >> "$calls"; }
  reset() { echo reset >> "$calls"; }
  destroy() { echo destroy >> "$calls"; }
  run_lifecycle_regression_cycles 3
  expected="$(printf 'start\nsmoke\nreset\nsmoke\ndestroy\n%.0s' 1 2 3)"
  [ "$(cat "$calls")" = "$expected" ]
  rm -f "$calls"
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

self_test_destroy_final_state() (
  cleanup() { :; }
  project_container_ids() { :; }
  project_volume_names() { :; }
  network_exists() { return 1; }
  is_kali_running() { return 0; }
  is_kali_connected() { return 1; }
  destroy >/dev/null
)

self_test_wait_healthy_disappearing_id
self_test_wait_healthy_replacement
self_test_wait_healthy_timeout
self_test_proxy_recovery_is_bounded
self_test_proxy_recovery_failure_is_bounded
self_test_three_cycle_sequence
self_test_cleanup_waits_for_absence
self_test_destroy_final_state

echo "PHASE2_LIFECYCLE_SELF_TEST_OK"
