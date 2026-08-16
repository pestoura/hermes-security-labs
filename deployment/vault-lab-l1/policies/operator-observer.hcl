path "sys/health" {
  capabilities = ["read"]
}

path "sys/seal-status" {
  capabilities = ["read"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "sys/mounts/transit" {
  capabilities = ["read"]
}

path "transit/keys/hermes-lab-l1-signer" {
  capabilities = ["read"]
}
