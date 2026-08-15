# Hermes Security Labs — governed live lifecycle acceptance runbook

**Scope:** standalone local Docker lifecycle acceptance only  
**Applies initially to:** WebGoat/WebWolf, DVWA/MariaDB and OWASP Juice Shop  
**Runtime authority:** none  
**Runner/signer promotion:** explicitly out of scope

This runbook generalises the accepted CHG-HSL-064 WebGoat/WebWolf lifecycle method so that the remaining labs can be validated with the same evidence and safety boundary rather than with ad-hoc operator steps.

It does **not** authorise a target effect, Kali scan, exploitation, signer/trust activation, policy enablement or Runner promotion. A lifecycle acceptance proves only that the exact tested lab revision can be provisioned, observed, reset and removed safely on the authorised local Docker host.

## 1. Acceptance invariant

A lab may be recorded as `PASS / ACCEPTED-LIVE-LIFECYCLE` only when one fresh run proves, against one exact repository revision:

```text
preflight PASS
  -> start PASS
  -> status PASS
  -> smoke PASS
  -> reset PASS
  -> status PASS
  -> smoke PASS
  -> destroy PASS
  -> destroy PASS (idempotent)
  -> zero-residue PASS
  -> non-interference PASS
  -> evidence-manifest PASS
```

Missing, interrupted or unrecoverable evidence is `UNKNOWN`/`NOT_RUN`, never inferred as PASS. A failed lifecycle step remains FAIL even when cleanup subsequently succeeds.

## 2. Supported lab parameters

| Lab | Canonical directory | Compose project | Host-port override | Internal target(s) | Lifecycle-only tracking |
| --- | --- | --- | --- | --- | --- |
| WebGoat/WebWolf | `platform/environments/web-api/webgoat` | `webgoat` | `WEBGOAT_HOST_PORT`, `WEBWOLF_HOST_PORT` | WebGoat `8080`, WebWolf `9090` | accepted by CHG-HSL-064 |
| DVWA/MariaDB | `platform/environments/web-api/dvwa` | `dvwa` | `DVWA_HOST_PORT` | DVWA `80`, MariaDB `3306` internal only | issue #393 |
| Juice Shop | `platform/environments/web-api/juice-shop` | `juice-shop` | `JUICE_SHOP_HOST_PORT` | Juice Shop `3000` | issue #394 |

Host-port overrides change only the localhost publication. Container-internal targets remain unchanged.

## 3. Preflight — mandatory before mutation

### 3.1 Exact repository revision

1. Read the current authoritative `origin/main` SHA.
2. Record that exact SHA in the run baseline.
3. Do not run from a stale, detached or dirty working tree.
4. Do not `reset`, `stash`, `clean` or overwrite unrelated work merely to obtain a clean tree.
5. Use a temporary clean export of the exact revision (`git archive` or an equivalent content-preserving mechanism) when the canonical checkout contains unrelated work.
6. All lifecycle scripts for the run must come from that same exact export.

If `origin/main` changes after the run starts, the run remains evidence only for the SHA recorded at preflight. Never relabel it as acceptance for a later revision.

### 3.2 Concurrency

Confirm that no other mutating lane is operating on the same Compose project. Read-only inspection may coexist; two lifecycle mutations may not.

If ownership or concurrency is ambiguous, stop before mutation and report `BLOCKED`.

### 3.3 Docker ownership boundary

Before mutation, inventory only what is needed to determine lab ownership:

- containers owned by the expected Compose project;
- volumes owned by the expected Compose project;
- networks owned by the expected Compose project;
- current localhost port listeners relevant to the lab.

A resource using the same image is **not** automatically owned by the lab. Ownership must be derived from the canonical Compose project/resource contract, not image similarity or a convenient name.

Non-owned resources must be preserved. The lifecycle run must never stop, remove, reconnect or modify them to make the test pass.

### 3.4 Host-port selection

Use the documented default only when it is free on `127.0.0.1`. If occupied, use the lab's supported host-port override and select a verified-free high localhost port.

The same override value(s) must be present for every lifecycle step in the run, including reset and destroy.

No acceptance run may widen publication from `127.0.0.1` to `0.0.0.0`, a LAN address or an external interface to avoid a port conflict.

### 3.5 Kali and target traffic

Standalone lifecycle acceptance does not connect Kali. Do not execute scanning, exploitation, authentication attempts or vulnerability exercises during this run.

Kali validation is a separate authorised evidence class and must not be silently bundled into lifecycle acceptance.

## 4. Canonical execution sequence

From the exact-revision temporary export, use only the lab's versioned scripts:

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/smoke.sh
./scripts/reset.sh
./scripts/status.sh
./scripts/smoke.sh
./scripts/destroy.sh
./scripts/destroy.sh
```

The second `destroy.sh` is mandatory evidence of idempotence, not optional cleanup.

Do not replace a failing canonical script with hand-written Docker commands to obtain a PASS. Diagnostic read-only commands are allowed; remediation that changes the tested lifecycle requires a repository change and a fresh run.

## 5. Failure handling

### Failure before the first mutation

- result: `BLOCKED` or `NOT_RUN`;
- do not run cleanup against non-owned or ambiguous resources;
- record the blocker and leave unrelated resources unchanged.

### Failure after mutation begins

1. preserve the failing step and exit code;
2. do not rewrite the run result to PASS;
3. if ownership remains unambiguous, invoke only the lab's canonical cleanup/destroy path;
4. collect zero-residue evidence after cleanup;
5. classify the lifecycle itself as FAIL and the cleanup separately as PASS/FAIL.

A successful destroy after a failed reset proves cleanup safety; it does not prove reset acceptance.

## 6. Lab-specific acceptance checks

### WebGoat/WebWolf

- both services healthy/readable through the documented localhost publications;
- WebWolf uses its canonical health/smoke path rather than `/`;
- both host publications remain loopback-only;
- canonical project network semantics remain intact;
- final project-owned containers, volumes and networks: zero.

CHG-HSL-064 is the reference accepted execution for this pattern.

### DVWA/MariaDB

- DVWA and MariaDB both reach healthy state;
- DVWA host publication is loopback-only and uses the effective `DVWA_HOST_PORT` mapping;
- MariaDB has **no host publication**;
- `dvwa-db` remains the internal database network;
- Kali remains disconnected from DVWA networks during lifecycle-only acceptance;
- after destroy: no project-owned DVWA/MariaDB containers, project volume or DVWA networks remain.

### Juice Shop

- container reaches healthy state using the internal port `3000`;
- host publication resolves to `127.0.0.1:<effective JUICE_SHOP_HOST_PORT>`;
- smoke uses the actual Compose mapping rather than assuming host port `3000`;
- canonical owned network is `juice-shop-lab`;
- Kali remains disconnected during lifecycle-only acceptance;
- after destroy: no project-owned Juice Shop container, volumes or network remain.

## 7. Zero-residue proof

The final proof must be gathered **after both destroy calls** and must establish at minimum:

- zero containers owned by the lab Compose project;
- zero lab-owned volumes expected to be removed by `destroy.sh`;
- zero lab-owned networks expected to be removed by `destroy.sh`;
- chosen localhost override port(s) are no longer listening because of the lab;
- Kali is not attached to a lab network;
- unrelated baseline resources remain present and unchanged in the dimensions observed before the run;
- the pinned image may remain cached and is not classified as residue.

Prefer Compose project labels and canonical resource identities over broad name matching.

## 8. Sanitised evidence set

Use an ephemeral local evidence directory outside Git. The accepted WebGoat pattern uses these logical artefacts:

```text
baseline.txt
01-start.log
02-status1.log
03-smoke1.log
04-reset.log
05-status2.log
06-smoke2.log
07-destroy1.log
08-destroy2.log
final-proof.txt
```

The contents must be sanitised and bounded. Do not capture or commit:

- credentials or secrets;
- cookies, tokens or session identifiers;
- raw application/database contents;
- vulnerability solutions or exploit payloads;
- scanner/offensive raw output;
- unrelated service logs.

## 9. Deterministic evidence manifest

After the run, calculate a deterministic read-only manifest over the sanitised evidence files.

Canonical line format:

```text
<sha256>  <size-bytes>  <relative-path>\n
```

Rules:

1. sort entries lexicographically by relative path;
2. hash each evidence file with SHA-256;
3. record exact byte size;
4. concatenate the canonical lines with LF endings;
5. calculate SHA-256 of the complete manifest bytes;
6. persist only the per-file metadata and aggregate manifest digest in the repository acceptance record unless a separately approved Evidence Plane custody path is used.

The manifest digest binds the acceptance record to the observed local evidence set. An ephemeral `/tmp` evidence directory is **not** WORM/durable custody and must never be represented as such.

## 10. Repository persistence after PASS

Only after a complete PASS may the result be persisted through a dedicated change/PR containing:

- a `VAL-HSL-<LAB>-LIVE-LIFECYCLE` validation campaign with exact tested commit;
- one resolved lifecycle observation;
- a sanitised acceptance record under `docs/roadmap/`;
- change record referencing the dedicated lifecycle campaign;
- walking-skeleton reconciliation;
- no raw runtime evidence;
- no change to Runner/signer promotion semantics.

The repository PR must independently pass its normal exact-head CI/security gates. Repository CI validates the persistence contract; it does not retroactively create the live evidence.

## 11. Acceptance boundary

A standalone lab lifecycle PASS proves only:

- exact-revision provisioning;
- readiness/smoke;
- reset;
- idempotent cleanup;
- loopback publication/isolation properties exercised by the canonical scripts;
- zero project-owned residue and bounded non-interference.

It does **not** prove:

- Runner dispatch;
- TB1 authorization delivery;
- signer or trust-store readiness;
- Evidence Plane durable custody;
- PRE/POST promotion packages;
- HITL approval consumption;
- vulnerability exploitability;
- pentest-tool coverage;
- production readiness.

These remain separate evidence classes and must stay fail-closed until independently observed.