import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "deployment" / "authorization-audit-live" / "probe.py"
POLICY = ROOT / "platform" / "evidence-plane" / "authorization-audit-custody-policy.yaml"


def _load_probe():
    assert PROBE.exists(), "authorization-audit live probe is not implemented yet"
    spec = importlib.util.spec_from_file_location("chg_hsl_090_live_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_probe_persists_reopens_verifies_and_cleans(tmp_path: Path) -> None:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    assert policy["state"] == "DISABLED"
    assert policy["runtime_status"] == "NOT_RUN"

    probe_root = tmp_path / "runtime-proof"
    result = _load_probe().run_probe(probe_root)
    assert result == {
        "schema_version": "hsl.authorization-audit-live-proof/v1",
        "runtime_status": "OBSERVED_SYNTHETIC_CUSTODY",
        "policy_source_state": "DISABLED",
        "effective_probe_state": "ENABLED_EPHEMERAL",
        "custody_persisted": True,
        "reopen_verified": True,
        "audit_chain_verified": True,
        "classification": "restricted",
        "record_count": 1,
        "execution_authority": "NONE",
        "promotion_allowed": False,
        "target_effect": "none",
        "cleanup_verified": True,
    }
    assert not probe_root.exists()


def test_cli_outputs_only_sanitized_result(tmp_path: Path, capsys) -> None:
    probe = _load_probe()
    rc = probe.main(["--root", str(tmp_path / "cli-proof")])
    captured = capsys.readouterr()
    assert rc == 0
    document = json.loads(captured.out)
    assert document["runtime_status"] == "OBSERVED_SYNTHETIC_CUSTODY"
    forbidden = ("evidence_id", "evidence_ref", "authorization_ref", "root", "path")
    assert not any(token in captured.out.lower() for token in forbidden)
    assert captured.err == ""


def test_existing_root_is_refused_without_deletion(tmp_path: Path) -> None:
    probe = _load_probe()
    root = tmp_path / "existing"
    root.mkdir()
    sentinel = root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    try:
        probe.run_probe(root)
    except probe.LiveProbeError as exc:
        assert str(exc) == "PROBE_ROOT_EXISTS"
    else:
        raise AssertionError("pre-existing root must be refused")
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_internal_failure_is_sanitized_and_cleans_owned_root(tmp_path: Path, monkeypatch) -> None:
    probe = _load_probe()
    original_load = probe._load
    real_adapter = original_load("chg_hsl_090_test_adapter", probe.ADAPTER_PATH)

    class FailingAdapter:
        def __init__(self, **_kwargs):
            pass

        def record_event(self, **_kwargs):
            raise RuntimeError("/secret/path/token")
    class FailingAdapterModule:
        AuthorizationAuditContext = real_adapter.AuthorizationAuditContext
        CanonicalAuthorizationAuditAdapter = FailingAdapter

    def load(name, path):
        if Path(path).resolve() == probe.ADAPTER_PATH.resolve():
            return FailingAdapterModule
        return original_load(name, path)

    monkeypatch.setattr(probe, "_load", load)
    root = tmp_path / "owned"
    try:
        probe.run_probe(root)
    except probe.LiveProbeError as exc:
        assert str(exc) == "PROBE_FAILED"
        assert "/secret/path/token" not in str(exc)
    else:
        raise AssertionError("internal failure must fail closed")
    assert not root.exists()
