# TB1 authorization signer / trust-store deployment preflight

This block turns two remaining live-promotion prerequisites into a machine-checkable **deployment declaration**:

1. the Hermes TB1 issuer is bound to a controlled external signing provider;
2. the Runner-side authorization trust store contains the matching purpose-bound public verification key.

It does **not** provision a provider, install a trust store, expose private-key material, enable receipt delivery or promote any Runner policy.

## Canonical command

```bash
python3 deployment/runtime-promotion/tb1_authorization_preflight.py \
  --descriptor deployment/runtime-promotion/templates/tb1-authorization-deployment-descriptor.example.yaml \
  --json check
```

Exit `0` means only that the declaration is internally consistent. Exit `2` is fail-closed. A PASS always retains `runtime_status: NOT_RUN`.

## Required declaration

The descriptor is strict and additional fields are refused. It fixes:

- `authority: hermes-control-plane`;
- `domain: hex0r.tb1.authorization.v1`;
- `purpose: tb1-authorization`;
- `runtime_status: NOT_RUN`;
- an external provider kind (`KMS`, `HSM`, `VAULT` or `PKCS11`);
- a non-secret logical provider reference;
- the signer `key_id` and algorithm (`Ed25519` or `ECDSA-P256-SHA256`);
- `private_key_local: false`;
- a restricted absolute trust-store install path below `/etc`, `/run` or `/var/run`;
- the canonical public-key trust-store document.

The trust-store document is validated against `platform/authorization-contract/authorization-trust-store.schema.json` and must remain purpose/domain separated from RoE signing.

## Fail-closed checks

The preflight refuses or reports findings for:

- unknown descriptor fields or any runtime status other than `NOT_RUN`;
- local private-key declarations;
- secret/private-shaped fields such as password, token, seed, credential or private key;
- provider references containing query strings, fragments, credentials or whitespace;
- trust-store schema/domain/purpose mismatch;
- duplicate key IDs;
- missing or non-active signer key;
- signer/trust-store algorithm mismatch;
- malformed public-key DER or a public key whose type does not match the declared algorithm;
- invalid trust-key validity windows;
- trust-store paths outside the permitted configuration/runtime roots.

The CLI output is sanitized and never prints the public-key document.

## What PASS does not prove

A repository PASS is still **GREEN-REPO**, not live acceptance. It does not prove that:

- the declared provider exists;
- the provider reference resolves to the intended production key;
- the private key is actually HSM/KMS/Vault protected;
- the trust-store file has been installed with correct owner/mode;
- the Runner process is using that trust store;
- an issued receipt can cross the live AF_UNIX delivery boundary;
- revocation/rotation works live;
- any Runner transport/routing/delivery policy has been promoted.

Those remain separate host/runtime evidence and explicit promotion gates.

## Files

- `tb1-authorization-deployment-descriptor.schema.json` — strict deployment declaration schema;
- `templates/tb1-authorization-deployment-descriptor.example.yaml` — inert example with public verification material only;
- `tb1_authorization_preflight.py` — pure read-only validator;
- `deployment/tests/test_tb1_authorization_preflight.py` — negative and positive repository proofs.
