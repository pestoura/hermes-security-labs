#!/usr/bin/env bash
set -euo pipefail

IMAGE="hermes/runtime-base-candidate:ci"
CONTEXT="platform/runtime-base/candidate"

cleanup() {
  docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build --pull=false --tag "$IMAGE" "$CONTEXT" >/dev/null

image_user="$(docker image inspect "$IMAGE" --format '{{.Config.User}}')"
test "$image_user" = "10001:10001"

probe_json="$({
  docker run --rm \
    --read-only \
    --cap-drop=ALL \
    --security-opt no-new-privileges:true \
    --network none \
    --pids-limit 64 \
    --memory 128m \
    --cpus 0.5 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
    --tmpfs /run:rw,noexec,nosuid,nodev,size=4m,mode=1777 \
    --tmpfs /var/tmp/hermes:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
    "$IMAGE"
} 2>/dev/null)"

PROBE_JSON="$probe_json" python - <<'PY'
import json
import os

probe = json.loads(os.environ["PROBE_JSON"])

assert probe["uid"] == 10001, probe
assert probe["gid"] == 10001, probe
assert probe["root_write_allowed"] is False, probe
assert probe["runner_root_write_allowed"] is False, probe
assert probe["tmp_write_allowed"] is True, probe
assert probe["run_write_allowed"] is True, probe
assert probe["state_write_allowed"] is True, probe
assert probe["cap_eff"] == "0000000000000000", probe
assert probe["no_new_privs"] == "1", probe
assert probe["raw_socket_available"] is False, probe
assert probe["tcp_socket_available"] is True, probe

print("RUNTIME_BASE_CANDIDATE_ACCEPTANCE_OK")
PY
