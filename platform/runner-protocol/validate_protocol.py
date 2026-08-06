#!/usr/bin/env python3
"""Validate Runner Protocol v2 messages using the canonical repository-local SDK."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    load_schema,
    validate_compatibility_matrix,
    validate_semantics,
)


def _load_message(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ProtocolValidationError(f"{path}: protocol message must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="JSON messages to validate")
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="validate the schema and compatibility matrix without message files",
    )
    args = parser.parse_args()

    load_schema()
    validate_compatibility_matrix()
    for path in args.files:
        validate_semantics(_load_message(path))
        print(f"RUNNER_PROTOCOL_OK\t{path}")

    if args.contract_only or not args.files:
        print("RUNNER_PROTOCOL_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
