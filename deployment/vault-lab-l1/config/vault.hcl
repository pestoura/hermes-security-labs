ui = false
disable_mlock = true

storage "raft" {
  path    = "/vault/data"
  node_id = "hermes-lab-l1-vault-1"
}

listener "tcp" {
  address            = "0.0.0.0:8200"
  cluster_address    = "0.0.0.0:8201"
  tls_cert_file      = "/run/secrets/vault_lab_l1_server_cert"
  tls_key_file       = "/run/secrets/vault_lab_l1_server_key"
  tls_client_ca_file = "/run/secrets/vault_lab_l1_ca"
  tls_min_version    = "tls12"
}

api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"
