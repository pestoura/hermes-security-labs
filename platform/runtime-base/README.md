# Minimal non-root runtime base — controlled candidate

Repository-owned runtime-base candidate for `SVP2-C-01`.

## Implemented guarantees

- core runtime policy requires execution as a non-root UID;
- root filesystem is read-only for the controlled candidate;
- runner code lives under `/opt/hermes/runners` and is immutable at runtime;
- writable state is limited to explicit ephemeral/state paths outside the runner code root;
- host mounts and Docker socket access are forbidden;
- Linux capabilities are dropped by default;
- the core network profile uses TCP connect semantics and requires `nmap -sT` by default;
- `NET_RAW` exists only in an explicit, justified `raw-network` profile;
- privileged mode is forbidden;
- request fields cannot supply commands, argv, shell, cwd, environment or executables;
- browser and heavy-tool layers remain separate from core.

## Controlled CI evidence

PR #215 added a disposable runtime candidate built from a base image pinned by digest and exercised by the canonical `platform/tests` gate. The candidate runs with UID/GID `10001:10001`, `--read-only`, `--cap-drop=ALL`, `no-new-privileges`, `--network none` and bounded resources.

The runtime probe verifies that:

- the process is non-root;
- writes to the root filesystem and `/opt/hermes/runners` are refused;
- only the declared tmpfs/state locations are writable;
- effective Linux capabilities are zero;
- `NoNewPrivs` is enabled;
- raw sockets are unavailable;
- an ordinary TCP socket can still be created without establishing a network connection.

The candidate image is disposable and removed by the acceptance harness after each test.

## Deliberate non-claims

Image publication, SBOM generation, signing, provenance attestation, registry promotion/retirement, Hermes deployment, browser/heavy-tool runtime images and production operational readiness remain `NOT_RUN` / outside this candidate. No security tool, target, credential or customer environment is used by the runtime-base acceptance test.

`NO_DEPLOYED_RUNTIME_CHANGE`.
