#!/usr/bin/env bash
set -euo pipefail
export TMPDIR=/home/estourpm/hermes-labs/kali-mcp/data/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
cd /home/estourpm/hermes-labs/kali-mcp
printf '=== compose source ===\n'
sha256sum compose.yaml
nl -ba compose.yaml | sed -n '1,220p'
printf '\n=== compose effective ===\n'
docker compose -p hermes-kali-mcp config --quiet
docker compose -p hermes-kali-mcp config > data/results/final-compose-effective.yaml
sed -n '1,260p' data/results/final-compose-effective.yaml
printf '\n=== container runtime ===\n'
docker ps --filter name=hermes-kali-mcp --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker image inspect --format 'ID={{.Id}} Size={{.Size}} CreatedAt={{.Created}}' hermes/kali-mcp:0.2.0 || true
printf '\n=== mcp config ===\n'
python3 - <<'PY'
from pathlib import Path
import yaml
p = Path.home()/'.hermes/profiles/pentest-lab/config.yaml'
data = yaml.safe_load(p.read_text())
block = ((data.get('mcp_servers') or {}).get('kali-lab') or {})
print('command=', block.get('command'))
print('args=', block.get('args'))
print('enabled=', block.get('enabled'))
print('timeout=', block.get('timeout'))
print('connect_timeout=', block.get('connect_timeout'))
print('supports_parallel_tool_calls=', block.get('supports_parallel_tool_calls'))
print('tools=', block.get('tools'))
PY
printf '\n=== mcp pentest-lab ===\n'
hermes -p pentest-lab mcp list > data/results/final-mcp-list.log 2>&1 || true
sed -n '1,220p' data/results/final-mcp-list.log
printf '\n=== mcp test ===\n'
hermes -p pentest-lab mcp test kali-lab > data/results/final-mcp-test.log 2>&1 || true
sed -n '1,260p' data/results/final-mcp-test.log
printf '\n=== mcp default ===\n'
hermes -p default mcp list > data/results/final-default-mcp-list.log 2>&1 || true
sed -n '1,220p' data/results/final-default-mcp-list.log
