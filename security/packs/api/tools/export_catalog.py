#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="runbooks/catalog.csv.gz")
    parser.add_argument("--output")
    args = parser.parse_args()
    with gzip.open(Path(args.source), "rt", encoding="utf-8") as handle:
        content = handle.read()
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
