# LANE C — CI / release / assurance optimization metrics

Scope: accelerate feedback on `hermes-security-labs` CI without weakening security
posture or hiding failures. Independent of #53. All changes are in CI workflow
definitions, tests, and this document — no package credentials, runtime images, or
accepted digests were modified.

## Invariants enforced (fail-closed)

- Every third-party / first-party action reference is pinned to a full 40-hex commit SHA.
  Mutable tags (`@v4`, `@v5`, `@v2`) are rejected by the new hygiene gate.
- Every job declares an explicit `timeout-minutes` bound.
- Every event-triggered workflow declares a `concurrency` group.
- `cancel-in-progress` is never unconditionally `true`, so post-merge `push` runs on
  `main` (exact-SHA evidence) are never cancelled.
- The `validate` workflow aggregates every gate into an `evidence` job that runs
  `if: always()` and fails closed, recording the exact `GITHUB_SHA`.

## Changes per workflow

| Workflow | Change | Security impact |
|---|---|---|
| `validate.yaml` | Split single `repository` job into 4 independent parallel jobs (`contracts`, `runner-protocol`, `runtime`, `security`) + `evidence` aggregator | None — same steps, faster (parallel) |
| `validate.yaml` | Added `pip` cache keyed on `platform/runner-protocol/pyproject.toml` + `security/pyproject.toml` | None — cache is read-only for installs |
| `validate.yaml` | Deterministic YAML parse: assert `count > 0`, skip `.git/` | Removes silent empty-parse pass |
| `validate.yaml` | Pinned `actions/checkout@v4`, `actions/setup-python@v5` to SHA | Supply-chain hardening |
| `validate.yaml` | Added `evidence` job: fail-closed exact-SHA gate | Stronger auditability |
| `security.yaml` | Pinned `gitleaks/gitleaks-action@v2` to SHA; added `permissions`, `concurrency`, `timeout-minutes: 15` | Hardening + bounded run |
| `private-vampi-source-repo-deny.yml` | Pinned `docker/setup-buildx-action` to SHA; added `concurrency` | Hardening |
| `container-build.yaml` | Pinned checkout; added `permissions`, `timeout-minutes: 30` | Hardening |
| `issue10/18/4/5`, `svp2-b03/c02/i01` | Pinned checkout/setup-python/upload-artifact; added `permissions`, `concurrency`, `timeout-minutes` | Hardening + bounded runs |
| `test-minimal.yaml`, `test-workflow.yaml` | Deleted (dead scaffolding; duplicated and unpinned) | Removes noise / supply-chain surface |
| `publish-*.yml` (5) | Untouched — already SHA-pinned, timeout + least-privilege `packages: write`, `cancel-in-progress: false` | No change |

## New assurance gate

`platform/tests/test_ci_workflow_hygiene.py` parametrizes over every workflow in
`.github/workflows/` and asserts the invariants above. It runs inside the existing
`contracts` job (`python -m pytest -q platform/tests`), so any future regression in
SHA-pinning, timeouts, concurrency, or permissions fails CI.

## Before / after (estimated; confirm in CI run)

| Metric | Before | After |
|---|---|---|
| `validate` jobs | 1 sequential (`repository`, ~all gates in series) | 4 parallel + 1 evidence aggregator |
| Wall-clock for `validate` (est.) | sum of all gate times | max(single gate time) + evidence |
| Workflows with `concurrency` | 5 (`publish-*`) | 15 (5 publish + 10 event-triggered) |
| Workflows with explicit `timeout-minutes` on every job | partial | 100% |
| Third-party actions pinned to SHA | trivy, partial gitleaks | all (checkout, setup-python, upload-artifact, gitleaks, buildx) |
| Exact-SHA evidence gate | implicit (push runs) | explicit fail-closed `evidence` job |
| CI hygiene regression protection | none | automated pytest gate |

## Exact-SHA validation

After merge, the `evidence` job on the `main` push run records `GITHUB_SHA` and fails
closed unless `contracts`, `runner-protocol`, `runtime`, and `security` all succeed.
The merged commit SHA must equal the `GITHUB_SHA` recorded in that run's summary.
