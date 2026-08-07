# Minimal non-root runtime base — contract candidate

Repository-owned policy candidate for `SVP2-C-01`.

## Implemented guarantees

- core runtime must execute as a non-root UID;
- root filesystem is declared read-only;
- runner code lives under `/opt/hermes/runners` and is immutable at runtime;
- writable state is limited to explicit ephemeral/state paths outside the runner code root;
- host mounts and Docker socket access are forbidden;
- Linux capabilities are dropped by default;
- the core network profile uses TCP connect semantics and requires `nmap -sT` by default;
- `NET_RAW` exists only in an explicit, justified `raw-network` profile;
- privileged mode is forbidden;
- request fields cannot supply commands, argv, shell, cwd, environment or executables;
- browser and heavy-tool layers remain separate from core.

## Deliberate non-claims

No image is built or promoted by this block. Container start, non-root observation, read-only-root observation and capability-drop observation remain `NOT_RUN` until validated against the selected runtime image and Hermes deployment path.

`NO_RUNTIME_CHANGE`.
