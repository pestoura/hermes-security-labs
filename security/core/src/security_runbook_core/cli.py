from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import load_pack
from .validation import validate_pack


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("pack")
    validate.add_argument("--schema", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("pack")

    args = parser.parse_args()
    if args.command == "validate":
        errors = validate_pack(Path(args.pack), Path(args.schema))
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"VALID: {len(load_pack(Path(args.pack)))} runbooks")
    else:
        for item in load_pack(Path(args.pack)):
            print(json.dumps(item["metadata"], sort_keys=True))
