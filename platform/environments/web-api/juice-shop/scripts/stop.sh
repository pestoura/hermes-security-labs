#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

echo "[stop] Stopping juice-shop..."
docker compose -f "${COMPOSE_FILE}" stop

echo "[stop] Status after stop:"
docker compose -f "${COMPOSE_FILE}" ps
