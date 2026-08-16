#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'CHG-HSL-082 capability verification refused: %s\n' "$*" >&2
  exit 1
}

command -v vault >/dev/null 2>&1 || fail "vault CLI is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
[[ "${VAULT_ADDR:-}" == https://* ]] || fail "VAULT_ADDR must use TLS"
[[ -z "${VAULT_SKIP_VERIFY:-}" ]] || fail "TLS verification bypass is forbidden"
[[ -n "${VAULT_CACERT:-}" && -r "${VAULT_CACERT}" ]] || fail "trusted LAB_L1 CA certificate is required"

status_file=$(mktemp)
key_file=$(mktemp)
sign_file=$(mktemp)
cleanup() {
  rm -f "$status_file" "$key_file" "$sign_file"
}
trap cleanup EXIT

vault status -format=json >"$status_file" || fail "Vault must report initialized=true and sealed=false"
vault read -format=json transit/keys/hermes-lab-l1-signer >"$key_file" || fail "exact Transit signer key is not readable"

python3 - "$status_file" "$key_file" <<'PY'
import hashlib
import json
import sys

status = json.load(open(sys.argv[1], encoding="utf-8"))
obj = json.load(open(sys.argv[2], encoding="utf-8"))
data = obj.get("data") or {}

if status.get("initialized") is not True or status.get("sealed") is not False:
    raise SystemExit("unexpected initialization/seal state")
if status.get("storage_type") != "raft":
    raise SystemExit("unexpected storage type")
if data.get("type") != "ed25519":
    raise SystemExit("unexpected Transit key type")
if data.get("derived") is not False:
    raise SystemExit("Transit key must be non-derived")
if data.get("exportable") is not False:
    raise SystemExit("Transit key must not be exportable")
if data.get("allow_plaintext_backup") is not False:
    raise SystemExit("plaintext backup must remain disabled")
if data.get("supports_signing") is not True:
    raise SystemExit("Transit key does not support signing")

latest = str(data.get("latest_version"))
entry = (data.get("keys") or {}).get(latest) or {}
public_key = entry.get("public_key")
if not isinstance(public_key, str) or "BEGIN PUBLIC KEY" not in public_key:
    raise SystemExit("latest Ed25519 public key is missing")

report = {
    "schema_version": "vault-lab-l1-capability/v1",
    "initialized": True,
    "sealed": False,
    "storage_type": "raft",
    "key_name": "hermes-lab-l1-signer",
    "key_type": "ed25519",
    "key_version": int(latest),
    "derived": False,
    "exportable": False,
    "allow_plaintext_backup": False,
    "supports_signing": True,
    "public_key_pem_sha256": hashlib.sha256(public_key.encode("utf-8")).hexdigest(),
}
print(json.dumps(report, sort_keys=True, separators=(",", ":")))
PY

assert_denied_read() {
  local path=$1
  if vault read "$path" >/dev/null 2>&1; then
    fail "signer credential unexpectedly read forbidden path: $path"
  fi
  printf 'VAULT_LAB_L1_DENY_OK path=%s\n' "$path"
}

assert_denied_read sys/mounts
assert_denied_read sys/auth
assert_denied_read sys/policies/acl
assert_denied_read transit/keys/hermes-lab-l1-unrelated

probe=$(printf '%s' 'CHG-HSL-082 capability probe' | base64 | tr -d '\n')
vault write -format=json transit/sign/hermes-lab-l1-signer input="$probe" >"$sign_file" || fail "signing probe failed"

python3 - "$sign_file" <<'PY'
import base64
import hashlib
import json
import sys

obj = json.load(open(sys.argv[1], encoding="utf-8"))
signature = ((obj.get("data") or {}).get("signature"))
if not isinstance(signature, str) or not signature.startswith("vault:v"):
    raise SystemExit("invalid Transit signature envelope")
parts = signature.split(":", 2)
if len(parts) != 3:
    raise SystemExit("invalid Transit signature envelope")
raw = base64.b64decode(parts[2], validate=True)
if len(raw) != 64:
    raise SystemExit("unexpected Ed25519 signature length")
print(
    json.dumps(
        {
            "schema_version": "vault-lab-l1-sign-probe/v1",
            "signature_version": parts[1],
            "signature_sha256": hashlib.sha256(raw).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

printf '%s\n' "VAULT_LAB_L1_CAPABILITY_VERIFIED"
