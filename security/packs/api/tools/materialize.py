#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from api_pentest_runbooks.catalog import load_runbooks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist/runbooks")
    args = parser.parse_args()
    root = Path(args.root)
    output = root / args.output
    output.mkdir(parents=True, exist_ok=True)
    for runbook in load_runbooks(root / "runbooks"):
        runbook.pop("_source", None)
        category = runbook["metadata"]["category"]
        destination = output / category / f"{runbook['metadata']['id'].lower()}.yaml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(yaml.safe_dump(runbook, sort_keys=False), encoding="utf-8")
    print(f"materialized {len(load_runbooks(root / 'runbooks'))} runbooks into {output}")


if __name__ == "__main__":
    main()
