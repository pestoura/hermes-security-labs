#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

EPIC_START = re.compile(r"(?=^  - id: SVP2-[A-Z]-\d{2}$)", re.MULTILINE)
ID_RE = re.compile(r"^  - id: (SVP2-[A-Z]-\d{2})$", re.MULTILINE)
STATUS_RE = re.compile(r"^    status: (\w+)$", re.MULTILINE)


class ReconciliationError(RuntimeError):
    pass


def reconcile(*, backlog_path: Path, plan_path: Path) -> list[str]:
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(plan.get("complete"), list):
        raise ReconciliationError("plan.complete must be a list")
    targets = [str(value) for value in plan["complete"]]
    if len(targets) != len(set(targets)) or not targets:
        raise ReconciliationError("plan targets must be unique and non-empty")
    reference = str(plan.get("completion_reference", "")).strip()
    if not reference.startswith("docs/"):
        raise ReconciliationError("completion_reference must be a docs/ path")

    original = backlog_path.read_text(encoding="utf-8")
    pieces = EPIC_START.split(original)
    seen: set[str] = set()
    output: list[str] = []

    for block in pieces:
        match = ID_RE.search(block)
        if not match or match.group(1) not in targets:
            output.append(block)
            continue
        epic_id = match.group(1)
        seen.add(epic_id)
        status = STATUS_RE.search(block)
        if not status or status.group(1) != "implementing":
            raise ReconciliationError(f"{epic_id}: expected implementing status")
        updated, count = re.subn(
            r"^    status: implementing$",
            "    status: completed",
            block,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ReconciliationError(f"{epic_id}: status replacement failed")
        updated, label_count = re.subn(
            r'"status:implementing"',
            '"status:completed"',
            updated,
            count=1,
        )
        if label_count != 1:
            raise ReconciliationError(f"{epic_id}: status label replacement failed")
        if reference not in updated:
            stripped = updated.rstrip()
            if "\n    references:\n" not in stripped:
                raise ReconciliationError(f"{epic_id}: references section missing")
            updated = stripped + f"\n      - {reference}\n\n"
        output.append(updated)

    missing = sorted(set(targets) - seen)
    if missing:
        raise ReconciliationError("targets not found: " + ",".join(missing))

    result = "".join(output).rstrip() + "\n"
    for epic_id in targets:
        block_match = re.search(
            rf"^  - id: {re.escape(epic_id)}$.*?(?=^  - id: SVP2-|\Z)",
            result,
            flags=re.MULTILINE | re.DOTALL,
        )
        if not block_match:
            raise ReconciliationError(f"{epic_id}: reconciled block missing")
        block = block_match.group(0)
        if "    status: completed" not in block or '"status:completed"' not in block:
            raise ReconciliationError(f"{epic_id}: reconciliation verification failed")
        if reference not in block:
            raise ReconciliationError(f"{epic_id}: completion reference missing")

    backlog_path.write_text(result, encoding="utf-8")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog", default="roadmap/epics/security-validation-platform-v2.yaml")
    parser.add_argument("--plan", default="roadmap/reconciliation/svp2-final-plan.yaml")
    args = parser.parse_args()
    changed = reconcile(backlog_path=Path(args.backlog), plan_path=Path(args.plan))
    print("SVP2_RECONCILED\t" + ",".join(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
