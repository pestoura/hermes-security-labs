#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
VAMPI_LIFECYCLE="${REPO_ROOT}/platform/environments/web-api/vampi/scripts/lifecycle.sh"
KALI_COMPOSE="${REPO_ROOT}/kali-mcp/compose.yaml"
PRIVATE_IMAGE="ghcr.io/pestoura/hermes-private-vampi@sha256:b1b66324a2d35cfe55e3edcd81f9f3c012907c71367df37f83d9ef63b500b3d3"
PUBLIC_ROLLBACK_IMAGE="ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229"
PACKAGE_REPOSITORY="pestoura/hermes-private-vampi"
RUNTIME_ROOT="${REPO_ROOT}/.runtime/issue53-private-vampi"
EVIDENCE_ROOT="${REPO_ROOT}/.runtime/evidence/issue53-private-vampi"

mode="${1:-plan}"
shift || true
username=""
approval_ref=""
publisher_private_confirmed=false
package_access_confirmed=false
prove_public_rollback=false

auth_dir=""
run_dir=""
override_file=""
kali_started_by_harness=false
private_lab_started=false

usage() {
  cat <<'EOF'
Usage:
  deployment/private-ghcr-vampi-acceptance.sh plan
  deployment/private-ghcr-vampi-acceptance.sh accept \
    --username <github-user> \
    --approval-ref <non-secret-reference> \
    --publisher-private-confirmed \
    --package-access-confirmed \
    [--prove-public-rollback]

For `accept`, provide the PAT classic as a single line on stdin. The token must
have exactly `read:packages`. Never place it in command arguments, environment
variables, Git, evidence, issue comments, or shell tracing.
EOF
}

record() {
  printf '%s\n' "$*"
  if [ -n "${run_dir}" ]; then
    printf '%s\n' "$*" >> "${run_dir}/acceptance.txt"
  fi
}

fail() {
  record "FAIL: $*"
  exit 1
}

cleanup() {
  local rc=$?
  set +e
  if [ "${private_lab_started}" = true ] && [ -n "${override_file}" ] && [ -f "${override_file}" ]; then
    DOCKER_CONFIG="${auth_dir:-${DOCKER_CONFIG:-}}" VAMPI_COMPOSE_OVERRIDE="${override_file}" "${VAMPI_LIFECYCLE}" destroy >/dev/null 2>&1 || true
  fi
  if [ "${kali_started_by_harness}" = true ]; then
    docker compose -p hermes-kali-mcp -f "${KALI_COMPOSE}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ -n "${auth_dir}" ] && [ -d "${auth_dir}" ]; then
    rm -rf "${auth_dir}"
  fi
  unset GHCR_PAT 2>/dev/null || true
  exit "$rc"
}
trap cleanup EXIT INT TERM

case "${mode}" in
  plan)
    cat <<EOF
ISSUE53_PRIVATE_GHCR_ACCEPTANCE_PLAN
Gate F: verify exact PAT scope, login via stdin, pull exact private digest.
Gate G: request pull,push registry scope without uploading content; require push to be absent.
Gate H: create an ignored .runtime Compose override, run VAmPI lifecycle parity, connect Kali only to the active lab, then destroy twice.
Private digest: ${PRIVATE_IMAGE}
Public rollback digest: ${PUBLIC_ROLLBACK_IMAGE}
Required manual gates before token read: publisher-private-confirmed + package-access-confirmed + approval-ref.
Versioned Compose mutation: none.
Package mutation: none.
EOF
    exit 0
    ;;
  accept) ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

while [ "$#" -gt 0 ]; do
  case "$1" in
    --username)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      username="$2"
      shift 2
      ;;
    --approval-ref)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      approval_ref="$2"
      shift 2
      ;;
    --publisher-private-confirmed)
      publisher_private_confirmed=true
      shift
      ;;
    --package-access-confirmed)
      package_access_confirmed=true
      shift
      ;;
    --prove-public-rollback)
      prove_public_rollback=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[ "${publisher_private_confirmed}" = true ] || fail "publisher private visibility confirmation is required before credential handling"
[ "${package_access_confirmed}" = true ] || fail "manual package repository-access confirmation is required before credential handling"
[ -n "${approval_ref}" ] || fail "a non-secret approval reference is required"
[[ "${approval_ref}" =~ ^[A-Za-z0-9._:/#-]+$ ]] || fail "approval reference contains unsupported characters"
[ -n "${username}" ] || fail "GitHub username is required"
[[ "${username}" =~ ^[A-Za-z0-9-]+$ ]] || fail "GitHub username contains unsupported characters"

for command in git docker curl python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "required command not found: ${command}"
done

docker compose version >/dev/null 2>&1 || fail "docker compose is unavailable"
[ -x "${VAMPI_LIFECYCLE}" ] || fail "VAmPI lifecycle script is unavailable or not executable"
[ -f "${KALI_COMPOSE}" ] || fail "Kali Compose definition is missing"

baseline_status="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)"
[ -z "${baseline_status}" ] || fail "Git working tree must be clean before private GHCR acceptance"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="${EVIDENCE_ROOT}/${timestamp}"
auth_dir="${RUNTIME_ROOT}/auth-${timestamp}-$$"
mkdir -p "${run_dir}" "${auth_dir}"
chmod 700 "${run_dir}" "${auth_dir}"
: > "${run_dir}/acceptance.txt"
chmod 600 "${run_dir}/acceptance.txt"

record "decision=ISSUE53_PRIVATE_VAMPI_ACCEPTANCE"
record "approval_ref=${approval_ref}"
record "publisher_private_confirmed=true"
record "package_access_confirmed=true"
record "private_image=${PRIVATE_IMAGE}"
record "credential_source=stdin"
record "credential_value_recorded=false"
record "package_mutation_performed=false"
record "versioned_compose_mutation_performed=false"

if [ -t 0 ]; then
  fail "PAT must be supplied non-interactively as a single line on stdin"
fi
IFS= read -r GHCR_PAT || true
[ -n "${GHCR_PAT:-}" ] || fail "empty PAT received on stdin"
[[ "${GHCR_PAT}" != *$'\n'* ]] || fail "invalid multiline PAT input"

netrc_file="${auth_dir}/netrc"
headers_file="${auth_dir}/github-headers"
umask 077
printf 'machine api.github.com login %s password %s\n' "${username}" "${GHCR_PAT}" > "${netrc_file}"
chmod 600 "${netrc_file}"

curl --fail --silent --show-error \
  --netrc-file "${netrc_file}" \
  --dump-header "${headers_file}" \
  --output /dev/null \
  https://api.github.com/user || fail "GitHub token scope introspection failed"

scopes="$(python3 - "${headers_file}" <<'PY'
from pathlib import Path
import sys
for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    if line.lower().startswith("x-oauth-scopes:"):
        print(line.split(":", 1)[1].strip())
        break
PY
)"
[ -n "${scopes}" ] || fail "GitHub did not expose X-OAuth-Scopes; minimum-scope proof is unavailable"

scope_result="$(python3 - "${scopes}" <<'PY'
import sys
scopes={item.strip() for item in sys.argv[1].split(',') if item.strip()}
required={'read:packages'}
forbidden={'write:packages','delete:packages','repo','workflow','admin:org'}
if scopes != required:
    print('FAIL')
    raise SystemExit(1)
if scopes & forbidden:
    print('FAIL')
    raise SystemExit(1)
print('PASS')
PY
)" || fail "PAT must have exactly read:packages and no additional scopes"
[ "${scope_result}" = PASS ] || fail "PAT scope verification failed"
record "gate_f_pat_scope=PASS_EXACT_READ_PACKAGES"

printf 'machine ghcr.io login %s password %s\n' "${username}" "${GHCR_PAT}" > "${netrc_file}"
chmod 600 "${netrc_file}"

granted_actions="$(
  curl --fail --silent --show-error \
    --netrc-file "${netrc_file}" \
    --get \
    --data-urlencode 'service=ghcr.io' \
    --data-urlencode "scope=repository:${PACKAGE_REPOSITORY}:pull,push" \
    https://ghcr.io/token |
  python3 - "${PACKAGE_REPOSITORY}" <<'PY'
import base64, json, sys
repo=sys.argv[1]
try:
    response=json.load(sys.stdin)
    token=response.get('token') or response.get('access_token')
    if not isinstance(token, str) or token.count('.') < 2:
        raise ValueError('registry token is not an inspectable JWT')
    payload=token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    decoded=json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    actions=[]
    for entry in decoded.get('access', []):
        if entry.get('type') == 'repository' and entry.get('name') == repo:
            actions.extend(entry.get('actions', []))
    if not actions:
        raise ValueError('no repository actions found in registry token')
    print(','.join(sorted(set(actions))))
except Exception:
    raise SystemExit(3)
PY
)" || fail "could not prove granted registry actions without mutation"

case ",${granted_actions}," in
  *,push,*) fail "read-only credential unexpectedly received push authority" ;;
esac
case ",${granted_actions}," in
  *,pull,*) ;;
  *) fail "read-only credential did not receive pull authority" ;;
esac
record "gate_g_registry_actions=PASS_PULL_WITHOUT_PUSH"

printf '%s' "${GHCR_PAT}" | DOCKER_CONFIG="${auth_dir}" docker login ghcr.io --username "${username}" --password-stdin >/dev/null || fail "GHCR read-only login failed"
unset GHCR_PAT
rm -f "${netrc_file}" "${headers_file}"

DOCKER_CONFIG="${auth_dir}" docker pull "${PRIVATE_IMAGE}" >/dev/null || fail "exact private digest pull failed"
private_image_id="$(DOCKER_CONFIG="${auth_dir}" docker image inspect "${PRIVATE_IMAGE}" --format '{{.Id}}')"
repo_digests="$(DOCKER_CONFIG="${auth_dir}" docker image inspect "${PRIVATE_IMAGE}" --format '{{join .RepoDigests " "}}')"
[[ "${repo_digests}" == *"sha256:b1b66324a2d35cfe55e3edcd81f9f3c012907c71367df37f83d9ef63b500b3d3"* ]] || fail "pulled image is not bound to the accepted private digest"
record "gate_f_exact_digest_pull=PASS"
record "private_image_id=${private_image_id}"

mkdir -p "${RUNTIME_ROOT}"
chmod 700 "${RUNTIME_ROOT}"
override_file="${RUNTIME_ROOT}/compose.private-vampi.${timestamp}.yaml"
cat > "${override_file}" <<EOF
services:
  vampi:
    image: ${PRIVATE_IMAGE}
EOF
chmod 600 "${override_file}"

if docker inspect hermes-kali-mcp --format '{{.State.Status}}' 2>/dev/null | grep -qx running; then
  record "kali_runtime=PREEXISTING"
else
  docker compose -p hermes-kali-mcp -f "${KALI_COMPOSE}" up -d kali-mcp >/dev/null
  kali_started_by_harness=true
  for _ in $(seq 1 36); do
    health="$(docker inspect hermes-kali-mcp --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || true)"
    [ "${health}" = healthy ] && break
    sleep 5
  done
  [ "${health:-}" = healthy ] || fail "Kali MCP did not become healthy"
  record "kali_runtime=STARTED_BY_HARNESS"
fi

export DOCKER_CONFIG="${auth_dir}"
export VAMPI_COMPOSE_OVERRIDE="${override_file}"

"${VAMPI_LIFECYCLE}" start
private_lab_started=true
"${VAMPI_LIFECYCLE}" smoke
"${VAMPI_LIFECYCLE}" status >/dev/null
"${VAMPI_LIFECYCLE}" connect-kali
"${VAMPI_LIFECYCLE}" connect-kali

docker exec -i hermes-kali-mcp python3 - <<'PY'
import http.client, socket
ip=socket.gethostbyname('vampi')
with socket.create_connection(('vampi',5000), timeout=5):
    pass
c=http.client.HTTPConnection('vampi',5000,timeout=5)
c.request('GET','/')
r=c.getresponse()
if r.status < 200 or r.status >= 500:
    raise SystemExit(f'unexpected HTTP status {r.status}')
r.read(); c.close()
print(f'KALI_PRIVATE_VAMPI_CONNECTIVITY_PASS dns={ip} http={r.status}')
PY
record "gate_h_kali_dns_tcp_http=PASS"

"${VAMPI_LIFECYCLE}" disconnect-kali
"${VAMPI_LIFECYCLE}" disconnect-kali
"${VAMPI_LIFECYCLE}" stop
"${VAMPI_LIFECYCLE}" start
"${VAMPI_LIFECYCLE}" smoke
"${VAMPI_LIFECYCLE}" reset
"${VAMPI_LIFECYCLE}" smoke
"${VAMPI_LIFECYCLE}" destroy
private_lab_started=false
"${VAMPI_LIFECYCLE}" destroy
record "gate_h_private_lifecycle=PASS"

if [ "${prove_public_rollback}" = true ]; then
  rollback_override="${RUNTIME_ROOT}/compose.public-rollback.${timestamp}.yaml"
  cat > "${rollback_override}" <<EOF
services:
  vampi:
    image: ${PUBLIC_ROLLBACK_IMAGE}
EOF
  chmod 600 "${rollback_override}"
  VAMPI_COMPOSE_OVERRIDE="${rollback_override}" "${VAMPI_LIFECYCLE}" start
  VAMPI_COMPOSE_OVERRIDE="${rollback_override}" "${VAMPI_LIFECYCLE}" smoke
  VAMPI_COMPOSE_OVERRIDE="${rollback_override}" "${VAMPI_LIFECYCLE}" destroy
  VAMPI_COMPOSE_OVERRIDE="${rollback_override}" "${VAMPI_LIFECYCLE}" destroy
  rm -f "${rollback_override}"
  record "public_rollback_control=PASS"
fi

rm -f "${override_file}"
override_file=""

after_status="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)"
[ "${after_status}" = "${baseline_status}" ] || fail "Git working tree changed during acceptance"
! docker network inspect vampi-lab >/dev/null 2>&1 || fail "VAmPI network residue remains"
! docker ps -a --format '{{.Names}}' | grep -qx 'vampi-vampi-1' || fail "VAmPI container residue remains"
record "zero_residue=PASS"
record "decision=READY_FOR_PRIVATE_VAMPI_COMPOSE_MIGRATION"
record "final=PASS"
