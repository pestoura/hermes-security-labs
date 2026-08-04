from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {"command", "script", "shell", "argv"}
PLACEHOLDERS = {"todo", "tbd", "profile-specific", "not-implemented", "example only"}


def load_runbooks() -> list[tuple[Path, dict[str, Any]]]:
    manifest = yaml.safe_load((ROOT / "pack.yaml").read_text(encoding="utf-8"))
    return [(path, yaml.safe_load(path.read_text(encoding="utf-8"))) for path in sorted(ROOT.glob(manifest["runbook_glob"]))]


def walk(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    elif isinstance(value, str):
        yield value


def validate() -> list[str]:
    manifest = yaml.safe_load((ROOT / "pack.yaml").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / manifest["schema"]).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    entries = load_runbooks()
    errors: list[str] = []
    if len(entries) != manifest["expected_runbooks"]:
        errors.append(f"expected {manifest['expected_runbooks']} runbooks, found {len(entries)}")
    ids: list[str] = []
    fingerprints: set[str] = set()
    for path, item in entries:
        rid = item.get("metadata", {}).get("id", "<missing>")
        ids.append(rid)
        for error in validator.iter_errors(item):
            errors.append(f"{path}: {error.json_path}: {error.message}")
        if path.stem != rid.lower():
            errors.append(f"{path}: filename does not match {rid}")
        walked = list(walk(item))
        keys = {value for value in walked if isinstance(value, str)}
        if FORBIDDEN.intersection(keys):
            errors.append(f"{path}: forbidden execution key")
        text = json.dumps(item, sort_keys=True).lower()
        if any(marker in text for marker in PLACEHOLDERS):
            errors.append(f"{path}: placeholder content remains")
        fp = json.dumps({"steps": item.get("steps"), "evaluation": item.get("evaluation")}, sort_keys=True)
        if fp in fingerprints:
            errors.append(f"{path}: duplicate steps/evaluation fingerprint")
        fingerprints.add(fp)
    if len(ids) != len(set(ids)):
        errors.append("duplicate runbook ids")
    return errors


def main() -> None:
    errors = validate()
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"VALID: {len(load_runbooks())} individually versioned experimental runbooks")


if __name__ == "__main__":
    main()
