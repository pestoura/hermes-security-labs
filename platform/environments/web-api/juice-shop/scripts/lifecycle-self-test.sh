#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIFECYCLE="$SCRIPT_DIR/lifecycle.sh"
export JUICE_SHOP_HOST_PORT=13000

# shellcheck source=platform/environments/web-api/juice-shop/scripts/lifecycle.sh
source "$LIFECYCLE"

self_test_smoke_rejects_connected_kali() (
  COMPOSE=(fake_compose)
  container_id() { echo lab-id; }
  assert_network_owned() { return 0; }
  is_kali_connected() { return 0; }
  python3() { cat >/dev/null; echo 200; }
  # Invoked indirectly through the COMPOSE command array.
  # shellcheck disable=SC2329
  fake_compose() {
    if [[ "$*" == "port juice-shop 3000" ]]; then
      echo "127.0.0.1:13000"
    fi
  }
  docker() {
    if [[ "$1" == "inspect" ]]; then echo healthy; return 0; fi
    if [[ "$1 $2" == "network inspect" ]]; then echo false; return 0; fi
    return 1
  }
  if smoke_lab >/dev/null 2>&1; then
    echo "smoke unexpectedly accepted connected Kali" >&2
    return 1
  fi
)

self_test_destroy_rejects_residual_container() (
  COMPOSE=(fake_compose)
  disconnect_kali() { :; }
  # Invoked indirectly through the COMPOSE command array.
  # shellcheck disable=SC2329
  fake_compose() {
    case "$*" in
      "down --volumes --remove-orphans") return 0 ;;
      "ps -aq") echo residual-container; return 0 ;;
    esac
    return 0
  }
  docker() { return 1; }
  if destroy_lab >/dev/null 2>&1; then
    echo "destroy unexpectedly accepted residual container" >&2
    return 1
  fi
)

self_test_destroy_rejects_residual_network() (
  COMPOSE=(fake_compose)
  disconnect_kali() { :; }
  # Invoked indirectly through the COMPOSE command array.
  # shellcheck disable=SC2329
  fake_compose() { return 0; }
  docker() {
    if [[ "$1 $2" == "network inspect" ]]; then return 0; fi
    return 1
  }
  if destroy_lab >/dev/null 2>&1; then
    echo "destroy unexpectedly accepted residual network" >&2
    return 1
  fi
)

self_test_smoke_rejects_connected_kali
self_test_destroy_rejects_residual_container
self_test_destroy_rejects_residual_network
echo "JUICE_SHOP_LIFECYCLE_SELF_TEST_OK"
