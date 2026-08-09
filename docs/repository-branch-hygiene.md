# Repository branch hygiene

How to account for remote branches in this repository without drawing wrong
conclusions from Git's built-in counters. Read-only: nothing described here
deletes or rewrites a reference.

## The problem with `--no-merged`

Pull requests in this repository are squash-merged. A squash merge creates a
*new* commit on `main` whose content equals the branch, but the branch's own
commits stay unreachable. Consequently:

- `git branch -r --merged origin/main` under-reports integrated branches.
- `git branch -r --no-merged origin/main` over-reports outstanding work.

Neither number is evidence. The reliable signal is `git cherry`, which compares
*patch content* instead of reachability: a branch whose every commit has an
equivalent patch already in the base carries no unique work, even when its tip
is unreachable.

## The inventory tool

```bash
python3 deployment/branch_inventory.py report
python3 deployment/branch_inventory.py report --base origin/main --output /tmp/branch-inventory.json
```

The tool fetches nothing; run `git fetch --prune origin` first if the
remote-tracking refs may be stale. Output is deterministic JSON sorted by
branch name, safe to diff between runs.

### Classification

| Classification | Meaning | Prune candidate |
| --- | --- | --- |
| `MERGED_REACHABLE` | the branch tip is an ancestor of the base ref | yes |
| `NO_UNIQUE_COMMITS` | not reachable, but every commit has an equivalent patch in the base (typical squash merge) | yes |
| `UNIQUE_COMMITS` | carries at least one patch absent from the base | no |
| `UNKNOWN` | the branch could not be evaluated | no |

`UNKNOWN` never becomes a prune candidate: absence of evidence is not evidence
of integration.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | no prune candidates |
| 1 | at least one prune candidate |
| 2 | at least one branch classified `UNKNOWN` |
| 3 | usage error (not a Git checkout) |

## Deletion policy

The tool produces a *candidate list*, not a decision. Deleting a remote branch
is a manual, separately authorised operation and is deliberately outside the
scope of this tooling. Before any deletion, confirm that:

1. the branch is `MERGED_REACHABLE` or `NO_UNIQUE_COMMITS` in a fresh report;
2. its pull request, if any, is merged or intentionally closed;
3. the branch is not referenced from an open issue, document or release note.

## Branch counts are not project state

A large branch count is repository hygiene, not outstanding delivery. Branch
inventories, `.deployment.json` and milestone counters are all *tracking*
metadata; none of them is evidence about whether a feature is implemented.
See [Deployment tracking and drift](deployment-tracking.md).

## Tests

```bash
python -m pytest -q deployment/tests -p no:cacheprovider
```

`deployment/tests/test_branch_inventory.py` builds throwaway upstream
repositories that reproduce the fast-forward, squash-merge and active-work
cases, and asserts that the tool never mutates references.
