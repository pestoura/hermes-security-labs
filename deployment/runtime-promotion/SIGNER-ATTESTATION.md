# TB1 external signer attestation — evidence-bound verifier

`runtime_signer_attestation.py` validates a normalized read-only observation of the external TB1 signing key against the accepted deployment descriptor. It is intentionally provider-neutral and performs **no provider API call**.

## What the verifier proves

For an `OBSERVED` envelope to pass, all of the following must hold:

- the canonical TB1 signer/trust-store deployment descriptor passes its existing preflight;
- provider kind, provider reference, key ID and algorithm exactly match the approved signer binding;
- the observed key is `active` and enabled for signing;
- the provider reports the private key as non-exportable;
- the SHA-256 fingerprint of the observed SubjectPublicKeyInfo (SPKI) equals the fingerprint of the public key already approved in the Runner authorization trust store;
- the observation timestamp is no more than five minutes old and is not materially in the future;
- the normalized observation contains no secret/private material fields;
- a separately injected `EvidenceVerifier` confirms that the source provider-metadata artefact exists at the declared `evidence://` reference with the declared SHA-256.

The verifier does not trust an attestation file merely because it exists. The default evidence verifier denies everything.

## Normalized observation contract

An external provider-specific collector may later map KMS, HSM, Vault or PKCS#11 metadata into the common attestation schema. That provider-specific collector is deliberately outside this lane.

The normalized envelope contains only:

- provider identity/reference;
- key identity and algorithm;
- key state and signing-enabled flag;
- whether the private key is exportable;
- public-key SPKI SHA-256;
- observation timestamp/source;
- reference and digest of the captured source evidence.

It contains no private key, credential, access token, secret or raw signing operation.

## Canonical example

`templates/tb1-signer-attestation.example.yaml` is deliberately `NOT_RUN` with no source evidence reference. It must not pass live attestation checks.

The CLI therefore remains fail-closed by default:

```bash
python3 deployment/runtime-promotion/runtime_signer_attestation.py \
  --deployment-descriptor deployment/runtime-promotion/templates/tb1-authorization-deployment-descriptor.example.yaml \
  --attestation deployment/runtime-promotion/templates/tb1-signer-attestation.example.yaml \
  --json check
```

A live orchestration path must inject an Evidence Plane-backed verifier and supply an externally captured `OBSERVED` envelope. Repository tests use a deterministic fake verifier only to exercise the contract.

## Non-claims

A repository PASS for this verifier does **not** mean the external signer has been observed live. Until an actual provider observation is captured and its evidence is verified:

- signer provider attestation remains `NOT_RUN`;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- host identity/socket/trust evidence remains separate;
- user-namespace evidence remains separate;
- unauthorized-peer negative acceptance remains separate;
- durable live audit/evidence backend proof remains separate;
- the bounded WebGoat L1 effect remains separate and requires explicit Human-in-the-Loop promotion.

`NO_RUNTIME_CHANGE`.
