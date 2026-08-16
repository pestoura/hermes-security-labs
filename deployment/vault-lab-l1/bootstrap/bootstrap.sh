#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DEPLOY_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
SIGNER_POLICY="$DEPLOY_DIR/policies/signer.hcl"
OBSERVER_POLICY="$DEPLOY_DIR/policies/operator-observer.hcl"
EXPECTED_VAULT_VERSION="Vault v1.21.4"
DEFAULT_ADDR="https://127.0.0.1:${VAULT_LAB_L1_HOST_PORT:-18200}"

fail() {
  printf 'CHG-HSL-082 bootstrap refused: %s\n' "$*" >&2
  exit 1
}

preflight() {
  command -v vault >/dev/null 2>&1 || fail "vault CLI is required on the operator host"
  command -v python3 >/dev/null 2>&1 || fail "python3 is required on the operator host"

  : "${VAULT_ADDR:=$DEFAULT_ADDR}"
  export VAULT_ADDR
  [[ "$VAULT_ADDR" == https://* ]] || fail "VAULT_ADDR must use https://"
  [[ -z "${VAULT_SKIP_VERIFY:-}" ]] || fail "VAULT_SKIP_VERIFY must be unset"
  [[ -n "${VAULT_CACERT:-}" ]] || fail "VAULT_CACERT must reference the LAB_L1 CA certificate"
  [[ -r "$VAULT_CACERT" ]] || fail "VAULT_CACERT is not readable"

  local version
  version=$(vault version 2>/dev/null || true)
  [[ "$version" == "$EXPECTED_VAULT_VERSION"* ]] || fail "operator vault CLI must be version 1.21.4"
}

require_unsealed() {
  local rc=0
  vault status >/dev/null 2>&1 || rc=$?
  [[ "$rc" -eq 0 ]] || fail "Vault must be initialized and unsealed for this operation"
}

require_initial_root() {
  vault token lookup -format=json | python3 -c '
import json, sys
obj = json.load(sys.stdin)
policies = set((obj.get("data") or {}).get("policies") or [])
raise SystemExit(0 if "root" in policies else 1)
' || fail "current credential is not the initial root token"
}

init_vault() {
  local rc=0
  if vault operator init -status >/dev/null 2>&1; then
    fail "Vault is already initialized; automatic re-initialization is forbidden"
  else
    rc=$?
  fi
  [[ "$rc" -eq 2 ]] || fail "unable to prove Vault is uninitialized"

  printf '%s\n' "Initialization output contains 3 Shamir shares and the initial root credential."
  printf '%s\n' "Capture them only in the approved operator custody channel; this script does not persist them."
  vault operator init -key-shares=3 -key-threshold=2
}

unseal_vault() {
  local index share
  for index in 1 2; do
    printf 'Enter Shamir share %s of threshold 2: ' "$index" >&2
    IFS= read -r -s share
    printf '\n' >&2
    [[ -n "$share" ]] || fail "empty Shamir share"
    printf '%s\n' "$share" | vault operator unseal >/dev/null
    unset share
  done
  require_unsealed
  printf '%s\n' "VAULT_LAB_L1_UNSEALED"
}

configure_vault() {
  require_unsealed
  require_initial_root

  vault secrets enable -path=transit transit
  vault write transit/keys/hermes-lab-l1-signer type=ed25519 derived=false exportable=false allow_plaintext_backup=false

  vault auth enable -path=approle approle
  vault policy write hermes-lab-l1-signer "$SIGNER_POLICY"
  vault policy write hermes-lab-l1-observer "$OBSERVER_POLICY"

  vault write auth/approle/role/hermes-lab-l1-signer \
    token_policies=hermes-lab-l1-signer \
    token_no_default_policy=true \
    token_ttl=10m \
    token_max_ttl=30m \
    secret_id_num_uses=1 \
    secret_id_ttl=10m

  vault write auth/approle/role/hermes-lab-l1-observer \
    token_policies=hermes-lab-l1-observer \
    token_no_default_policy=true \
    token_ttl=15m \
    token_max_ttl=30m \
    secret_id_num_uses=1 \
    secret_id_ttl=10m

  printf '%s\n' "VAULT_LAB_L1_BOOTSTRAP_CONFIGURED"
}

show_role_id() {
  require_unsealed
  require_initial_root
  local role=${1:-}
  case "$role" in
    signer)
      vault read -field=role_id auth/approle/role/hermes-lab-l1-signer/role-id
      ;;
    observer)
      vault read -field=role_id auth/approle/role/hermes-lab-l1-observer/role-id
      ;;
    *)
      fail "show-role-id requires signer or observer"
      ;;
  esac
}

issue_wrapped_secret_id() {
  require_unsealed
  require_initial_root
  local role=${1:-}
  case "$role" in
    signer)
      vault write -wrap-ttl=5m -f auth/approle/role/hermes-lab-l1-signer/secret-id
      ;;
    observer)
      vault write -wrap-ttl=5m -f auth/approle/role/hermes-lab-l1-observer/secret-id
      ;;
    *)
      fail "issue-wrapped-secret-id requires signer or observer"
      ;;
  esac
}

revoke_initial_root() {
  require_unsealed
  require_initial_root
  [[ "${HERMES_VAULT_LAB_L1_ROOT_REVOKE_CONFIRM:-}" == "OPERATIONAL_APPROLE_AUTH_VERIFIED" ]] || \
    fail "set HERMES_VAULT_LAB_L1_ROOT_REVOKE_CONFIRM=OPERATIONAL_APPROLE_AUTH_VERIFIED only after wrapped credentials were consumed and limited AppRole authentication was verified"
  vault token revoke -self
  unset VAULT_TOKEN || true
  printf '%s\n' "VAULT_LAB_L1_INITIAL_ROOT_REVOKED"
}

usage() {
  cat >&2 <<'EOF'
Usage: bootstrap.sh <preflight|init|unseal|configure|show-role-id|issue-wrapped-secret-id|revoke-root> [signer|observer]

Secret-bearing rules:
- init writes shares and the initial credential only to the operator terminal;
- unseal reads shares silently and sends them to Vault on stdin, never argv;
- wrapped SecretID responses are single-use and short-lived;
- revoke-root is gated until limited AppRole authentication has been independently verified.
EOF
  exit 2
}

main() {
  preflight
  local command=${1:-}
  case "$command" in
    preflight) printf '%s\n' "VAULT_LAB_L1_PREFLIGHT_OK" ;;
    init) init_vault ;;
    unseal) unseal_vault ;;
    configure) configure_vault ;;
    show-role-id) show_role_id "${2:-}" ;;
    issue-wrapped-secret-id) issue_wrapped_secret_id "${2:-}" ;;
    revoke-root) revoke_initial_root ;;
    *) usage ;;
  esac
}

main "$@"
