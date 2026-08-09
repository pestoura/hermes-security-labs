#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=kali-mcp/scripts/env.sh
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${PROJECT_DIR}/data/results"
BACKUP_DIR="${RESULTS_DIR}/../results-backup-$(date +%Y%m%dT%H%M%SZ)"

mkdir -p "${BACKUP_DIR}"
cp -a "${RESULTS_DIR}/." "${BACKUP_DIR}/"
echo "Backup created at ${BACKUP_DIR}"
