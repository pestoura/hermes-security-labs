"""Make the DevSecOps src-layout package importable in the pack test suite."""

from __future__ import annotations

import sys
from pathlib import Path

_PACK_ROOT = Path(__file__).resolve().parents[1]
for candidate in (_PACK_ROOT / "src", _PACK_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
