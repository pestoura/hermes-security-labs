from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/catalog.csv")
    args = parser.parse_args()
    manifest = yaml.safe_load((ROOT / "pack.yaml").read_text(encoding="utf-8"))
    paths = sorted(ROOT.glob(manifest["runbook_glob"]))
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "category", "status", "provider", "action", "profile", "severity"])
        writer.writeheader()
        for path in paths:
            item = yaml.safe_load(path.read_text(encoding="utf-8"))
            primary = item["steps"][1]
            writer.writerow({
                "id": item["metadata"]["id"], "name": item["metadata"]["name"],
                "category": item["metadata"]["category"], "status": item["metadata"]["status"],
                "provider": primary["provider"], "action": primary["action"], "profile": primary["profile"],
                "severity": item["outputs"]["severity"],
            })
    print(f"EXPORTED: {len(paths)} -> {output}")


if __name__ == "__main__":
    main()
