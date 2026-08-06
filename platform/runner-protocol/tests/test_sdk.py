from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

import runner_protocol_v2  # noqa: E402
from runner_protocol_v2 import ProtocolValidationError, contract_root  # noqa: E402


def test_public_sdk_version_and_exports() -> None:
    assert runner_protocol_v2.__version__ == "2.0.0"
    assert set(runner_protocol_v2.__all__) == {
        "LedgerConflictError",
        "LedgerDecision",
        "LedgerError",
        "LedgerRecord",
        "LedgerStateError",
        "LedgerUnavailableError",
        "PosixProcessSupervisor",
        "ProtocolValidationError",
        "SQLiteIdempotencyLedger",
        "SupervisedProcessResult",
        "SupervisedProcessSpec",
        "SupervisionError",
        "SupervisionSpecError",
        "SupervisionUnavailableError",
        "__version__",
        "classify_idempotency",
        "contract_root",
        "load_schema",
        "request_fingerprint",
        "validate_compatibility_matrix",
        "validate_progress_sequence",
        "validate_schema",
        "validate_semantics",
    }


def test_editable_source_resolves_canonical_contract_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNNER_PROTOCOL_CONTRACT_ROOT", raising=False)
    assert contract_root() == ROOT
    assert (contract_root() / "compatibility.yaml").is_file()
    assert (contract_root() / "schemas" / "runner-protocol-v2.schema.json").is_file()


def test_incomplete_explicit_contract_root_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNNER_PROTOCOL_CONTRACT_ROOT", str(tmp_path))
    with pytest.raises(ProtocolValidationError, match="canonical contract root"):
        contract_root()


def test_package_imports_in_clean_subprocess_via_sdk_path() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SDK_SRC)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runner_protocol_v2; print(runner_protocol_v2.__version__)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "2.0.0"


def test_cli_wrapper_does_not_duplicate_contract_logic() -> None:
    source = (ROOT / "validate_protocol.py").read_text(encoding="utf-8")
    for forbidden_definition in (
        "def validate_schema(",
        "def validate_semantics(",
        "def request_fingerprint(",
        "def validate_progress_sequence(",
    ):
        assert forbidden_definition not in source
    assert "from runner_protocol_v2 import" in source
