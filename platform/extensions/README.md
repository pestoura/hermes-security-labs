# Extension SDK and conformance contract candidate

Repository-owned contract candidate for `SVP2-K-01`.

## Extension families

- Capability Runner;
- Runtime Driver;
- Lab Driver;
- Evidence Adapter;
- Evaluator.

## Activation boundary

An extension is activation-eligible only when all of the following are true:

1. its manifest validates against the repository-owned schema;
2. all permissions are explicitly declared;
3. compatibility with the required protocol is declared;
4. the conformance suite has passed and its report is integrity-bound;
5. externally supplied signature-verification evidence is `verified`;
6. lifecycle state is `certified`;
7. the extension is neither quarantined, deprecated nor revoked.

No extension manifest may contain command-shaped execution fields such as `command`, `argv`, `shell`, `cwd`, `environment` or generic executable paths.

## Deliberate non-claims

This block does not load, import, install or execute third-party extensions. Production signature verification, extension loading, runtime isolation and production certification remain `NOT_RUN`. Certification performed by this contract is a deterministic decision over supplied evidence, not a cryptographic verification implementation.

`NO_RUNTIME_CHANGE`.
