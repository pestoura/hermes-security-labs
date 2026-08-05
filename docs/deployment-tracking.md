# Deployment tracking and drift detection

Configuration-integrity tooling that binds the configuration applied on the
server to a known Git commit and reports local differences. It never runs
laboratories, scanners or any offensive activity, and never stores file
contents or confidential values.

## Architecture

```
deployment/
├── deployment_tracking.py   # single implementation (deploy/verify/drift/rollback)
├── deploy.sh                # wrapper + exclusive flock
├── verify.sh                # wrapper, read-only
├── drift-check.sh           # wrapper, tri-state output
├── rollback.sh              # wrapper + exclusive flock
└── tests/                   # pytest, temporary directories only
```

The shell wrappers only resolve repository, target directory and lock, then
delegate to the Python module. Common logic (scope walk, hashing, atomic
writes, snapshots) lives in Python.

Environment overrides: `DEPLOY_TARGET_DIR`, `DEPLOY_REPO_DIR`,
`DEPLOY_LOCK_FILE`. Default target: `/home/estourpm/hermes-labs/hermes-security-labs`.
Default lock: `${TMPDIR:-/tmp}/security-labs-deployment-drift-issue7`.

## Approved scope

Directories: `config`, `deployment`, `kali-mcp`, `platform`, `security`.
Files: `compose.yaml`, `Makefile`, `Dockerfile`, `.env.example`, `.gitignore`.

Always excluded: `.git`, `__pycache__`, `.pytest_cache`, `.ruff_cache`,
`.venv`, `node_modules`, `evidence`, `runtime`, `state`, `tmp`, `cache`,
snapshots, plus environment/secret/archive/log/database patterns
(`.env`, `.env.*`, `*.key`, `*.pem`, `*.crt`, `*.p12`, `*.pfx`, `*.token`,
`*.secret`, `*.log`, `*.sqlite`, `*.db`, `*.bak*`, `*.tar*`, `*.zip`, `*.pyc`,
`compose-effective.yaml`, `container-inspect*.json`, `deployment.local.json`).
`.env.example` is the single explicit exception.

## State file `.deployment.json`

Written atomically (temp file + `fsync` + `os.replace`) with mode `0600`.
Schema version `1.0.0`.

| Field | Meaning |
| --- | --- |
| `schema_version` | state schema version |
| `tool_version` | tooling version that produced the state |
| `deployment_id` | UTC timestamp + short commit |
| `applied_at_utc` | UTC application time |
| `repository` | `pestoura/hermes-security-labs` |
| `git.commit` / `git.ref` | applied full SHA-1 and ref |
| `git.divergence` | upstream ahead/behind counters at deploy time |
| `target_dir` | directory where configuration was applied |
| `scope` | approved directories and files |
| `inventory` | relative path → `sha256`, `size`, `mode` |
| `runners` | SHA-256 of the three pack runners |
| `bindings` | path, SHA-256 and laboratory count of `security/bindings/labs.yaml` |
| `config_references` | SHA-256 of key configuration manifests |
| `previous_state` | previous deployment id, commit, snapshot dir, snapshot state hash |

The state never contains file contents. Keys matching secret-like hints
(`password`, `secret`, `token`, `api_key`, `authorization`, `cookie`,
`credential`, `private_key`) are rejected by schema validation.

## Commands

```bash
deployment/deploy.sh [--dry-run] [--target-dir=DIR] [--state-file=PATH]
deployment/verify.sh [--target-dir=DIR] [--state-file=PATH]
deployment/drift-check.sh [--target-dir=DIR] [--state-file=PATH]
deployment/rollback.sh [--dry-run] [--target-dir=DIR]
```

- `deploy` refuses a dirty working tree and upstream divergence, snapshots the
  previous deployment, copies only approved files through `*.deploytmp`
  staging and then writes the state transactionally.
- `verify` validates schema, permissions, commit, files, hashes, runners and
  bindings. It never repairs anything.
- `drift-check` returns strictly `IN_SYNC`, `DRIFT_DETECTED` or `UNKNOWN`.
  A missing state, invalid JSON, unknown commit or any unexpected error yields
  `UNKNOWN` — never `IN_SYNC`.
- `rollback` restores the validated previous snapshot, supports `--dry-run`,
  is transactional and refuses a dirty source tree.

## States and exit codes

| Code | Meaning |
| --- | --- |
| 0 | `IN_SYNC` / operation succeeded |
| 1 | `DRIFT_DETECTED` |
| 2 | `UNKNOWN` (absent, invalid or insufficient evidence) |
| 3 | usage error |
| 4 | precondition refused (dirty tree, divergence, no snapshot) |
| 5 | another operation holds the deployment lock (wrappers only) |

## Detected drift

Modified file, missing file, extra in-scope file, relevant permission change,
state file permissions other than `0600`, outdated or missing runner, changed
bindings or laboratory count, and commit mismatch against the checkout.

## Testing

```bash
python -m pytest -q deployment/tests -p no:cacheprovider
```

All tests build throwaway Git repositories and target directories under the
pytest `tmp_path`; the canonical checkout is never modified.

## Future periodic execution

`drift-check.sh` is side-effect free and safe for a periodic Hermes cron job.
Suggested contract: run it hourly, treat exit 1 and exit 2 as alerting
conditions, keep evidence outside Git, and never trigger automatic repair.
