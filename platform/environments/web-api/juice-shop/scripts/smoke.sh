#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../compose.yaml"

echo "[smoke] Checking container status..."
docker compose -f "${COMPOSE_FILE}" ps

echo "[smoke] Checking health status..."
health=$(docker inspect -f "{{.State.Health.Status}}" juice-shop 2>/dev/null || echo "none")
if [ "$health" != "healthy" ]; then
  echo "[smoke] Container not healthy: $health"
  exit 1
fi
echo "[smoke] Health: $health"

echo "[smoke] Testing HTTP connectivity..."
# Use Node.js for HTTP test (available in host)
node -e "
const http = require('http');
const req = http.get('http://127.0.0.1:3000', (res) => {
  const ok = res.statusCode >= 200 && res.statusCode < 500;
  res.resume();
  process.exit(ok ? 0 : 1);
});
req.on('error', () => process.exit(1));
req.setTimeout(3000, () => { req.destroy(); process.exit(1); });
" && echo "[smoke] HTTP OK" || {
  echo "[smoke] HTTP test failed"
  exit 1
}

echo "[smoke] All checks passed"
