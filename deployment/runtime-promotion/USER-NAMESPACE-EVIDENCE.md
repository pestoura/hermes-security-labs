# Runner user-namespace evidence — read-only boundary

`runtime_userns_evidence.py` observes Linux UID/GID namespace mappings for exactly two explicitly reviewed process IDs: the execution gateway and Runner.

It exists to answer one narrow live-promotion question:

> Do the actual processes named by the reviewed deployment evidence have the exact UID/GID maps and user-namespace relationship that were approved?

A repository or host PASS does **not** authorize Runner promotion.

## Inputs

The descriptor contains:

- a canonical Runner identity descriptor under `deployment/runtime-promotion/`;
- one explicit gateway PID;
- one distinct explicit Runner PID;
- exact expected `uid_map` entries for each PID;
- exact expected `gid_map` entries for each PID;
- whether both processes are expected to share or use different user namespaces.

There is deliberately no process name search, service discovery, container discovery or wildcard PID selection.

## Observation boundary

The real observer opens only `/proc/<explicit-pid>` and uses that directory file descriptor to read:

- `stat`, only to pin/check process start-time identity during the observation;
- `uid_map`;
- `gid_map`;
- `ns/user` inode metadata.

The PID directory and direct proc files are opened read-only with `O_NOFOLLOW` where applicable. The process start time is read before and after the mapping observation; a change fails closed.

The observer does **not** read:

- `cmdline`;
- `environ`;
- process memory;
- file descriptors;
- credentials or secrets;
- target/application payloads.

It does not use `sudo`, `setns`, `unshare`, `nsenter`, Docker, subprocesses, networking or filesystem mutation.

## Validation

For each role, the observer requires:

1. the referenced identity descriptor to pass the canonical Runner identity preflight;
2. non-overlapping reviewed UID/GID map ranges;
3. the reviewed map to cover the role's declared host UID/GID;
4. the observed map to equal the reviewed map exactly;
5. the observed map to cover the declared host UID/GID;
6. the gateway/Runner user-namespace relationship to match the reviewed expectation.

The result contains only PIDs, process start-time ticks, namespace inode IDs, UID/GID map integers and boolean coverage checks.

## Canonical command

```bash
python3 deployment/runtime-promotion/runtime_userns_evidence.py \
  --descriptor deployment/runtime-promotion/templates/runtime-userns-evidence-descriptor.example.yaml \
  --json check
```

The committed example contains placeholder PIDs and is intentionally **not expected to pass on an arbitrary host**. Live execution requires a reviewed descriptor bound to the actual authorized deployment processes.

## Non-claims

Even when `user_namespace_checks_passed=true`:

- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- #336 host identity/socket/trust-store evidence remains a separate evidence class;
- signer attestation remains separate;
- unauthorized-peer negative acceptance remains separate;
- durable live audit/evidence backend proof remains separate;
- the WebGoat L1 target effect remains separate and subject to Human-in-the-Loop promotion.

`NO_RUNTIME_CHANGE`.
