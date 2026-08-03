from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "security" / "tools" / "securityctl.py"
SPEC = importlib.util.spec_from_file_location("securityctl", MODULE_PATH)
assert SPEC and SPEC.loader
securityctl = importlib.util.module_from_spec(SPEC)
sys.modules["securityctl"] = securityctl
SPEC.loader.exec_module(securityctl)


def test_combined_catalog_is_valid():
    errors, warnings, entries = securityctl.perform_validation()
    assert errors == []
    assert len(entries) == 370
    assert warnings


def test_pack_counts_are_exact():
    entries = securityctl.load_runbooks()
    counts = {domain: sum(item.domain == domain for item in entries) for domain in securityctl.PACKS}
    assert counts == {"api": 150, "devsecops": 120, "ai-mcp": 100}


def test_global_runbook_ids_are_unique():
    entries = securityctl.load_runbooks()
    ids = [item.runbook_id for item in entries]
    assert len(ids) == len(set(ids))


def test_bindings_only_reference_known_campaigns():
    entries = securityctl.load_runbooks()
    errors, campaigns = securityctl.validate_campaigns(entries)
    assert errors == []
    binding_errors = securityctl.validate_bindings(campaigns)
    assert binding_errors == []
