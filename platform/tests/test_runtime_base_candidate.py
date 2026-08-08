from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "platform" / "runtime-base" / "candidate" / "validate_candidate_runtime.sh"


def test_controlled_non_root_runtime_base_candidate() -> None:
    completed = subprocess.run(
        ["bash", str(HARNESS)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert "RUNTIME_BASE_CANDIDATE_ACCEPTANCE_OK" in completed.stdout
