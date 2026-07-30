#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

PROJECT_NAME="webgoat"
COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")

echo "[stop] Disconnecting Kali from network..."
docker network disconnect webgoat-lab hermes-kali-mcp 2>/dev/null || true

echo "[stop] Stopping webgoat..."
"${COMPOSE[@]}" stop

echo "[stop] WebGoat stopped"
