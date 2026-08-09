"""Temporary-directory tests for the deployment tracking tooling.

No laboratory, scanner or network activity: everything runs on throwaway
directories created by pytest.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

DEPLOYMENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOYMENT_DIR))

import deployment_tracking as dt  # noqa: E402


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src"
    (repo / "security" / "packs" / "api" / "runner").mkdir(parents=True)
    (repo / "security" / "packs" / "devsecops" / "runner").mkdir(parents=True)
    (repo / "security" / "packs" / "ai-mcp" / "runner").mkdir(parents=True)
    (repo / "security" / "bindings").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)

    (repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (repo / "config" / "packages.txt").write_text("nmap\n", encoding="utf-8")
    for rel in dt.RUNNER_PATHS:
        (repo / rel).write_text(f"# runner {rel}\n", encoding="utf-8")
    (repo / dt.BINDINGS_PATH).write_text(
        "domains:\n  api:\n    laboratories:\n      - id: alpha\n      - id: beta\n",
        encoding="utf-8",
    )
    run_git(repo.parent, "init", "-q", str(repo))
    run_git(repo, "config", "user.email", "test@example.invalid")
    run_git(repo, "config", "user.name", "test")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "initial")
    return repo


@pytest.fixture()
def deployed(source_repo: Path, tmp_path: Path):
    target = tmp_path / "target"
    rc = dt.main(["deploy", "--repo", str(source_repo), "--target-dir", str(target)])
    assert rc == dt.EXIT_OK
    return source_repo, target, target / dt.STATE_FILENAME


def drift(target: Path, repo: Path | None = None) -> tuple[int, dict]:
    argv = ["drift-check", "--target-dir", str(target)]
    if repo:
        argv += ["--repo", str(repo)]
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = dt.main(argv)
    return rc, json.loads(buf.getvalue())


def test_state_file_shape_and_permissions(deployed):
    repo, target, state_file = deployed
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["schema_version"] == dt.STATE_SCHEMA_VERSION
    assert state["tool_version"] == dt.TOOL_VERSION
    assert len(state["git"]["commit"]) == 40
    assert state["previous_state"] is None
    assert len(state["runners"]) == 3
    assert state["bindings"]["laboratories"] == 2
    assert dt.validate_schema(state) == []


def test_state_has_no_secret_material(deployed):
    _, _, state_file = deployed
    raw = state_file.read_text(encoding="utf-8")
    state = json.loads(raw)
    assert not dt.contains_secret_like(state)
    # no file contents are stored, only digests
    assert "services: {}" not in raw


def test_secret_like_paths_do_not_invalidate_schema(deployed):
    """Inventory keys are paths; a path named 'secrets' is not a secret value."""
    _, _, state_file = deployed
    state = json.loads(state_file.read_text(encoding="utf-8"))
    entry = state["inventory"]["compose.yaml"]
    state["inventory"]["config/wrongsecrets-token.yaml"] = dict(entry)
    assert dt.validate_schema(state) == []


def test_secret_like_value_outside_inventory_is_rejected(deployed):
    _, _, state_file = deployed
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["git"]["api_token"] = "x"
    assert "state contains secret-like keys" in dt.validate_schema(state)


def test_inventory_entry_with_content_field_is_rejected(deployed):
    _, _, state_file = deployed
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["inventory"]["compose.yaml"]["content"] = "services: {}"
    assert any("unexpected fields" in p for p in dt.validate_schema(state))


def test_in_sync(deployed):
    repo, target, _ = deployed
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_OK
    assert report["status"] == "IN_SYNC"
    assert report["findings"] == []


def test_modified_file(deployed):
    repo, target, _ = deployed
    (target / "compose.yaml").write_text("services: {changed: 1}\n", encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert report["status"] == "DRIFT_DETECTED"
    assert {"type": "modified_file", "path": "compose.yaml"} in report["findings"]


def test_removed_file(deployed):
    repo, target, _ = deployed
    (target / "config" / "packages.txt").unlink()
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert any(f["type"] == "missing_file" for f in report["findings"])


def test_extra_file_in_scope(deployed):
    repo, target, _ = deployed
    (target / "config" / "extra.txt").write_text("x\n", encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert any(f["type"] == "extra_file" for f in report["findings"])


def test_mode_change_detected(deployed):
    repo, target, _ = deployed
    path = target / "config" / "packages.txt"
    os.chmod(path, 0o777)
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert any(f["type"] == "mode_changed" for f in report["findings"])


def test_missing_state_is_unknown(deployed):
    repo, target, state_file = deployed
    state_file.unlink()
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_UNKNOWN
    assert report["status"] == "UNKNOWN"


def test_invalid_json_is_unknown(deployed):
    repo, target, state_file = deployed
    state_file.write_text("{not json", encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_UNKNOWN
    assert report["status"] == "UNKNOWN"


def test_truncated_schema_is_unknown(deployed):
    repo, target, state_file = deployed
    state = json.loads(state_file.read_text(encoding="utf-8"))
    del state["inventory"]
    state_file.write_text(json.dumps(state), encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_UNKNOWN


def test_unknown_commit_is_unknown(deployed):
    repo, target, state_file = deployed
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["git"]["commit"] = "0" * 40
    state_file.write_text(json.dumps(state), encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_UNKNOWN
    assert report["status"] == "UNKNOWN"


def test_commit_mismatch_is_drift(deployed):
    repo, target, state_file = deployed
    (repo / "config" / "packages.txt").write_text("nmap\ncurl\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "second")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert any(f["type"] == "commit_mismatch" for f in report["findings"])


def test_in_sync_has_no_drift_class(deployed):
    repo, target, _ = deployed
    _, report = drift(target, repo)
    assert report["drift_class"] == dt.DRIFT_CLASS_NONE


def test_stale_checkout_is_classified_as_tracking_metadata_only(deployed):
    """A stale local checkout is expected drift, not a broken deployment."""
    repo, target, _ = deployed
    (repo / "config" / "packages.txt").write_text("nmap\ncurl\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "second")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert report["status"] == "DRIFT_DETECTED"
    assert report["drift_class"] == dt.DRIFT_CLASS_TRACKING_METADATA
    assert {f["type"] for f in report["findings"]} == {"commit_mismatch"}


def test_content_drift_outranks_tracking_metadata(deployed):
    repo, target, _ = deployed
    (repo / "config" / "packages.txt").write_text("nmap\ncurl\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "second")
    (target / "compose.yaml").write_text("services: {changed: 1}\n", encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert report["drift_class"] == dt.DRIFT_CLASS_CONTENT


def test_tracking_metadata_class_never_downgrades_the_status(deployed):
    """Classification is informational: it must not turn drift into IN_SYNC."""
    repo, target, _ = deployed
    (repo / "config" / "packages.txt").write_text("nmap\ncurl\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "second")
    rc, report = drift(target, repo)
    assert rc != dt.EXIT_OK
    assert report["status"] != "IN_SYNC"


def test_unknown_reports_unknown_drift_class(deployed):
    repo, target, state_file = deployed
    state_file.unlink()
    _, report = drift(target, repo)
    assert report["status"] == "UNKNOWN"
    assert report["drift_class"] == "UNKNOWN"


def test_classify_findings_is_pure_and_total():
    assert dt.classify_findings([]) == dt.DRIFT_CLASS_NONE
    assert dt.classify_findings([{"type": "commit_mismatch"}]) == dt.DRIFT_CLASS_TRACKING_METADATA
    assert dt.classify_findings([{"type": "modified_file"}]) == dt.DRIFT_CLASS_CONTENT
    assert dt.classify_findings([{"type": "unheard-of"}]) == dt.DRIFT_CLASS_CONTENT


def test_outdated_runner_detected(deployed):
    repo, target, _ = deployed
    (target / dt.RUNNER_PATHS[0]).write_text("# stale runner\n", encoding="utf-8")
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    types = {f["type"] for f in report["findings"]}
    assert "runner_outdated" in types


def test_bad_state_permissions_reported(deployed):
    repo, target, state_file = deployed
    os.chmod(state_file, 0o644)
    rc, report = drift(target, repo)
    assert rc == dt.EXIT_DRIFT
    assert any(f["type"] == "state_permissions" for f in report["findings"])


def test_deploy_refuses_dirty_tree(source_repo, tmp_path):
    (source_repo / "config" / "packages.txt").write_text("dirty\n", encoding="utf-8")
    rc = dt.main(["deploy", "--repo", str(source_repo), "--target-dir", str(tmp_path / "t2")])
    assert rc == dt.EXIT_PRECONDITION
    assert not (tmp_path / "t2" / dt.STATE_FILENAME).exists()


def test_dry_run_writes_nothing(source_repo, tmp_path):
    target = tmp_path / "dry"
    rc = dt.main(
        ["deploy", "--repo", str(source_repo), "--target-dir", str(target), "--dry-run"]
    )
    assert rc == dt.EXIT_OK
    assert not (target / dt.STATE_FILENAME).exists()


def test_failure_during_state_write_preserves_previous_state(deployed):
    repo, target, state_file = deployed
    before = state_file.read_bytes()
    (repo / "config" / "packages.txt").write_text("nmap\nnc\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "third")
    rc = dt.main(
        [
            "deploy",
            "--repo",
            str(repo),
            "--target-dir",
            str(target),
            "--fail-after-copy",
        ]
    )
    assert rc == dt.EXIT_UNKNOWN
    assert state_file.read_bytes() == before
    assert not list(target.glob("**/*.deploytmp"))


def test_rollback_between_two_known_states(deployed):
    repo, target, state_file = deployed
    first = json.loads(state_file.read_text(encoding="utf-8"))
    (repo / "config" / "packages.txt").write_text("nmap\nsqlmap\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", "fourth")
    assert dt.main(["deploy", "--repo", str(repo), "--target-dir", str(target)]) == dt.EXIT_OK
    second = json.loads(state_file.read_text(encoding="utf-8"))
    assert second["previous_state"]["deployment_id"] == first["deployment_id"]
    assert (target / "config" / "packages.txt").read_text(encoding="utf-8") == "nmap\nsqlmap\n"

    assert (
        dt.main(["rollback", "--target-dir", str(target), "--dry-run"]) == dt.EXIT_OK
    )
    assert json.loads(state_file.read_text(encoding="utf-8"))["deployment_id"] == second["deployment_id"]

    assert dt.main(["rollback", "--target-dir", str(target)]) == dt.EXIT_OK
    assert (target / "config" / "packages.txt").read_text(encoding="utf-8") == "nmap\n"
    restored = json.loads(state_file.read_text(encoding="utf-8"))
    assert restored["deployment_id"] == first["deployment_id"]
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600


def test_rollback_without_snapshot_refuses(deployed):
    repo, target, _ = deployed
    rc = dt.main(["rollback", "--target-dir", str(target)])
    assert rc == dt.EXIT_PRECONDITION


def test_default_lock_name_matches_issue7_contract(source_repo, tmp_path):
    # Issue #7 requires the exclusive lock name exactly:
    # security-labs-deployment-drift-issue7
    # The name is internal to the bash wrapper; it only surfaces in stderr
    # when lock acquisition fails. Hold the default lock first (forcing the
    # wrapper's default TMPDIR) and assert the contention message names it.
    import fcntl

    custom_tmp = tmp_path / "locktmp"
    custom_tmp.mkdir()
    env = dict(os.environ)
    env.pop("DEPLOY_LOCK_FILE", None)
    env["TMPDIR"] = str(custom_tmp)
    expected = custom_tmp / "security-labs-deployment-drift-issue7"
    lf = open(expected, "w")
    fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        target = tmp_path / "t-lockname"
        out = subprocess.run(
            ["bash", f"{DEPLOYMENT_DIR}/deploy.sh", f"--target-dir={target}", "--dry-run"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert out.returncode == 5, out.stderr
        assert "security-labs-deployment-drift-issue7" in out.stderr, out.stderr
    finally:
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        lf.close()


def test_concurrent_lock_is_exclusive(source_repo, tmp_path):
    lock = tmp_path / "concurrency.lock"
    target = tmp_path / "locked"
    env = dict(
        os.environ,
        DEPLOY_LOCK_FILE=str(lock),
        DEPLOY_TARGET_DIR=str(target),
        DEPLOY_REPO_DIR=str(source_repo),
    )
    cmd = f"bash {DEPLOYMENT_DIR}/deploy.sh --target-dir={target} --dry-run"
    free = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env)
    assert free.returncode == 0, free.stderr

    script = f"exec 9>{lock}; flock -n 9 || exit 9; {cmd}; rc=$?; exit $rc"
    held = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
    assert held.returncode == 5, held.stderr
    assert "lock" in held.stderr.lower()
