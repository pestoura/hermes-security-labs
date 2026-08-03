from __future__ import annotations

import csv
import gzip
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_pack(root: Path) -> list[dict[str, Any]]:
    manifest = load_yaml(root / "pack.yaml")
    catalog_path = root / manifest["catalog"]
    items: list[dict[str, Any]] = []
    with gzip.open(catalog_path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            item = {
                "apiVersion": manifest["apiVersion"],
                "kind": "SecurityRunbook",
                "metadata": {
                    "id": row["id"],
                    "name": row["name"],
                    "version": row.get("version") or "0.1.0",
                    "status": row.get("status") or "experimental",
                    "domain": manifest["domain"],
                    "category": row["category"],
                    "tags": [value for value in row.get("tags", "").split("|") if value],
                },
                "selectors": {
                    "target_types": [value for value in row["target_types"].split("|") if value],
                    "capabilities": [value for value in row["capabilities"].split("|") if value],
                },
                "risk": {
                    "intrusiveness": row["intrusiveness"],
                    "destructive": row["destructive"].lower() == "true",
                    "production_safe": row["production_safe"].lower() == "true",
                    "max_actions": int(row["max_actions"]),
                    "timeout_seconds": int(row["timeout_seconds"]),
                },
                "steps": [
                    {
                        "id": "primary",
                        "provider": row["provider"],
                        "action": row["action"],
                        "profile": row["profile"],
                        "arguments": {"target_ref": "{{ target.ref }}"},
                    }
                ],
                "evaluation": {
                    "vulnerable_when": ["profile-specific vulnerable signal"],
                    "secure_when": ["profile-specific protection signal"],
                    "inconclusive_when": ["prerequisite or evidence missing"],
                },
                "outputs": {
                    "title": row["name"],
                    "severity": row["severity"],
                    "confidence": "dynamic",
                },
            }
            items.append(item)

    ids = [item["metadata"]["id"] for item in items]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate runbook ids: {', '.join(duplicates)}")
    return items
