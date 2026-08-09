# Baseline known issues — reconciled 2026-08-09

This file reconciles the operational baseline imported on 2026-07-30 with the
repository state demonstrated on `main` through Lane N.

It is deliberately conservative: repository and CI evidence never substitutes
for live Hermes/Kali/runtime acceptance.

## Status model

- `RESOLVED-REPO` — the original repository defect is corrected and covered by
  the normal repository validation path. This does **not** imply a separate live
  runtime acceptance unless stated explicitly.
- `BLOCKED-ON-RUNTIME` — repository work can describe or prepare the contract,
  but closure requires an authorized live Hermes/lab/tool observation.
- `OPEN` — neither repository nor runtime evidence is sufficient to close the
  item.

## Reconciled imported baseline

### 1. SKILL.md — MCP URL format

**Status: `RESOLVED-REPO`**

`skills/kali-mcp-lab/SKILL.md` now requires exclusively
`@url:` with `http://127.0.0.1:5000` and explicitly rejects the bare and HTTPS
variants that caused the original ambiguity.

No live Kali MCP registration is claimed by this repository-only correction.

### 2. Juice Shop healthcheck depends on wget

**Status: `RESOLVED-REPO`**

The canonical Juice Shop Compose healthcheck no longer depends on `wget`. It
uses the image's Node runtime to perform the bounded loopback HTTP healthcheck.
The Compose contract is validated in CI.

This closes the imported repository defect; it does not replace an end-to-end
Hermes-host lifecycle acceptance.

### 3. WPScan writable state

**Status: `BLOCKED-ON-RUNTIME`**

The historical live Kali observation was that `wpscan --version` could not use
`/root/.wpscan` with the read-only root filesystem. The current repository does
not contain evidence proving a writable WPScan state path on the live Kali MCP
runtime.

Required closure evidence: authorized live tool-health/functional acceptance
showing the intended writable path while preserving read-only root, resource
limits and isolation.

### 4. Gobuster MCP execution validation

**Status: `BLOCKED-ON-RUNTIME`**

Binary presence or repository declaration is not functional acceptance. Closure
requires an authorized disposable lab target, bounded execution and captured
runtime evidence proving a successful Gobuster operation inside the isolated
Kali MCP path.

### 5. Dirb MCP execution validation

**Status: `BLOCKED-ON-RUNTIME`**

Closure requires the same class of authorized isolated runtime proof as
Gobuster. No repository-only result is promoted to `FUNCTIONAL-PASS`.

### 6. SQLMap synthetic SQLi target

**Status: `BLOCKED-ON-RUNTIME`**

The repository now contains a canonical DVWA synthetic SQL-injection scenario,
a typed `web.validation.sql-injection` semantic operation and a corresponding
tool-registry entry. However, the current typed gateway entry is still
`PRESENT` rather than `READY` and its controlled candidate effect is explicitly
not implemented.

This is useful contract progress but it does **not** close the original SQLMap
functional-acceptance gap. Closure requires an authorized local synthetic SQLi
target and live bounded validation evidence.

### 7. Hydra synthetic authentication target

**Status: `BLOCKED-ON-RUNTIME`**

No live disposable authentication service plus scoped synthetic credentials has
been accepted through the current runtime path. Do not create or reuse real
credentials merely to close this test.

### 8. John the Ripper synthetic hash

**Status: `BLOCKED-ON-RUNTIME`**

The historical run wrote state under `/root/.john`. Closure requires a live
isolated Kali acceptance proving an intentional writable state/cache path with
a synthetic hash and no weakening of the read-only-root boundary.

### 9. Enum4linux disposable Samba target

**Status: `BLOCKED-ON-RUNTIME`**

No accepted disposable Samba target and bounded live Enum4linux validation are
recorded. A reachable host alone is not authorization.

### 10. Metasploit writable state

**Status: `BLOCKED-ON-RUNTIME`**

The historical live runtime warned that `/root` was not writable. Closure
requires a live isolated acceptance proving the intended writable Metasploit
state path (for example a dedicated state mount/tmpfs) without broadening host
access, privileges or persistence.

### 11. Juice Shop end-to-end workflow

**Status: `BLOCKED-ON-RUNTIME`**

Repository contracts now cover canonical target authorization, Docker backend
planning, lifecycle, a Juice Shop readiness adapter, structured scenario
evidence expectations and reset/cleanup proof expectations. The aggregate JDS
static gate composes the seeded scenario set before expensive CI runtime jobs.

The original issue remains open because the full live Hermes walking skeleton
has not yet been accepted as one correlated run:

`authorize -> provision -> readiness -> execute bounded scenario -> evidence -> reset -> known-state proof`

### 12. Deployment drift detection

**Status: `BLOCKED-ON-RUNTIME`**

Repository deployment tooling and source-of-truth validation exist, but the
baseline item specifically requires comparison against the live Hermes host.
Closure therefore requires authorized host-level observation through the
runtime path; CI repository validation alone is insufficient.

## Repository walking-skeleton status after Lanes K-N

The following is demonstrated at repository/CI level and must not be read as
live Hermes acceptance:

| Contract | Repository status | Runtime status |
| --- | --- | --- |
| Scenario Plan Composer | `GREEN` — deterministic, inert, fail-closed | not an executor |
| Core web readiness adapters | `GREEN` — WebGoat/WebWolf, DVWA, Juice Shop declarations | `BLOCKED-ON-RUNTIME` acceptance |
| Structured scenario evidence contract | `GREEN` — aligned with Evidence Plane v2 policy | `BLOCKED-ON-RUNTIME` scenario evidence observation |
| Aggregate JDS static gate | `GREEN` — stages static contracts before Docker/runtime CI | not live Hermes proof |
| Target authorization boundary | `GREEN` repository contract | live execution still requires authorized target/window |
| Backend abstraction | Docker `SUPPORTED/READY`; other backends fail closed | VM/Kubernetes/Cloud/Remote remain not ready |

Merged repository checkpoints:

- Lane K — PR #294 — `f18428e96a6fa4ab9873c64336258e799d91de3f`;
- Lane L — PR #295 — `140f359f8ea72e8af0d335ab13ccafffca2f3d95`;
- Lane M — PR #296 — `2a10282780bcf5f333baf074feae614303f50abf`;
- Lane N — PR #297 — `da22a93f5f90938ba677cf185208af477bbab04c`.

## Separate open dependency — private read-only GHCR

GitHub issue #53 remains separate from the imported 12-item runtime baseline.
The strict/private consumption target still requires a classic GitHub credential
with exactly `read:packages` for the final Hermes production boundary, plus the
specified anonymous-deny/authenticated-read and negative write controls.

The temporary DEV exception for a broader PAT does not relax the strict target
state and does not block unrelated repository-only work.

## Runtime acceptance rule

When live acceptance resumes, do not convert a repository `GREEN` into runtime
`ACCEPTED` by inference. Re-observe Hermes health, canonical targets, isolation,
readiness, evidence and reset proof. If the approval path returns
`waiting_for_approval` with `approval_id = null`, do not bypass it or invent an
identifier; record the runtime blocker and preserve the safe state.
