from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import load_pack


def validate_pack(root: Path, schema_path: Path) -> list[str]:
    schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for runbook in load_pack(root):
        for error in validator.iter_errors(runbook):
            location = ".".join(str(part) for part in error.absolute_path)
            errors.append(f"{runbook['metadata']['id']}:{location}: {error.message}")
        for step in runbook["steps"]:
            arguments = step.get("arguments", {})
            forbidden = {"command", "script", "shell", "argv"}
            if forbidden.intersection(arguments):
                errors.append(f"{runbook['metadata']['id']}: free-form execution field present")
    return errors
