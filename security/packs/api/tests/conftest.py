"""Ensure API pack tests can import top-level evaluation helpers without extra env."""
import sys
from pathlib import Path

_API_PACK_ROOT = Path(__file__).resolve().parents[1]
if str(_API_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_PACK_ROOT))
