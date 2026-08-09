"""Contract gates for the declared AI/MCP runtime projection.

These tests are owned by the protocol side of the boundary. They assert that
the compatibility matrix declares the projection honestly and that the
declaration cannot silently diverge from the module on disk. Negative controls
prove each gate actually fails when the declaration or the module is weakened.
"""

from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    validate_compatibility_matrix,
)
from runner_protocol_v2.contracts import _validate_projection_module  # noqa: E402

COMPATIBILITY = ROOT / "compatibility.yaml"
MODULE_RELATIVE = (
    "security/packs/ai-mcp/src/ai_mcp_runbooks/runner_protocol_projection.py"
)
CAPABILITY_ID = "ai-mcp.runtime.handler-invoke"


def _ai_mcp_family() -> dict:
    data = yaml.safe_load(COMPATIBILITY.read_text(encoding="utf-8"))
    return {family["id"]: family for family in data["runner_families"]}["ai-mcp"]


def test_projection_is_declared_without_execution_or_promotion_claim() -> None:
    projection = _ai_mcp_family()["runtime_projection"]
    assert projection["status"] == "CONTRACT_PROJECTION_ONLY"
    assert projection["integration_scope"] == "pure_translation_boundary"
    assert projection["execution_integration"] == "NOT_RUN"
    assert projection["production_effect_claim"] == "none"
    assert projection["executes_runtime"] is False
    assert projection["network_access"] == "none"
    assert projection["subprocess_creation"] == "none"
    assert projection["evidence_payload"] == "digest_only"
    assert projection["authorization_source"] == "hermes_control_plane"
    assert projection["policy_effect"] == "narrow_or_refuse_only"


def test_projection_declaration_does_not_change_family_promotion_state() -> None:
    family = _ai_mcp_family()
    assert family["execution_integration"] == "NOT_RUN"
    assert family["promotion_status"] == "blocked"
    assert family["protocol_status"] == "conformance_only"


def test_declared_projection_module_exists_and_matches_the_matrix() -> None:
    projection = _ai_mcp_family()["runtime_projection"]
    module = REPO_ROOT / projection["module_path"]
    assert module.is_file()
    assert projection["capability_id"] in module.read_text(encoding="utf-8")


def test_compatibility_matrix_accepts_the_declared_projection() -> None:
    validate_compatibility_matrix()


def test_projection_gate_passes_for_the_real_module() -> None:
    _validate_projection_module(
        REPO_ROOT, relative_path=MODULE_RELATIVE, capability_id=CAPABILITY_ID
    )


@pytest.mark.parametrize(
    "injected",
    [
        "import subprocess\n",
        "from ai_mcp_runbooks.dispatch import dispatch\n",
        "from ai_mcp_runbooks.execution import LocalHttpTransport\n",
        "import socket\n",
    ],
)
def test_projection_gate_rejects_an_execution_capable_module(
    tmp_path: Path, injected: str
) -> None:
    """Negative control: the gate must fail when the module gains execution reach."""
    fake_root = tmp_path / "repo"
    target = fake_root / MODULE_RELATIVE
    target.parent.mkdir(parents=True)
    original = (REPO_ROOT / MODULE_RELATIVE).read_text(encoding="utf-8")
    target.write_text(injected + original, encoding="utf-8")
    with pytest.raises(ProtocolValidationError, match="must not import execution modules"):
        _validate_projection_module(
            fake_root, relative_path=MODULE_RELATIVE, capability_id=CAPABILITY_ID
        )


def test_projection_gate_rejects_a_legacy_executor_reference(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    target = fake_root / MODULE_RELATIVE
    target.parent.mkdir(parents=True)
    original = (REPO_ROOT / MODULE_RELATIVE).read_text(encoding="utf-8")
    target.write_text(original + "\n# execute_runbook\n", encoding="utf-8")
    with pytest.raises(ProtocolValidationError, match="must not reference execute_runbook"):
        _validate_projection_module(
            fake_root, relative_path=MODULE_RELATIVE, capability_id=CAPABILITY_ID
        )


def test_projection_gate_rejects_a_missing_capability_declaration(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    target = fake_root / MODULE_RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text(
        textwrap.dedent(
            '''
            """Projection without the declared capability."""
            '''
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProtocolValidationError, match="does not declare capability"):
        _validate_projection_module(
            fake_root, relative_path=MODULE_RELATIVE, capability_id=CAPABILITY_ID
        )


def test_projection_gate_rejects_a_missing_module(tmp_path: Path) -> None:
    with pytest.raises(ProtocolValidationError, match="missing or outside repository"):
        _validate_projection_module(
            tmp_path, relative_path=MODULE_RELATIVE, capability_id=CAPABILITY_ID
        )


def test_matrix_validation_fails_when_the_projection_declaration_is_weakened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control on the declaration itself, not only on the module."""
    fake_contract = tmp_path / "runner-protocol"
    shutil.copytree(ROOT, fake_contract, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    data = yaml.safe_load((fake_contract / "compatibility.yaml").read_text(encoding="utf-8"))
    for family in data["runner_families"]:
        if family["id"] == "ai-mcp":
            family["runtime_projection"]["executes_runtime"] = True
    (fake_contract / "compatibility.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setenv("RUNNER_PROTOCOL_CONTRACT_ROOT", str(fake_contract))
    with pytest.raises(ProtocolValidationError, match="runtime-projection declaration"):
        validate_compatibility_matrix()
