from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"

SECRET_KEYS = {
    "authorization",
    "api_key",
    "argv",
    "command",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "stderr",
    "stdout",
    "token",
}


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load("lane_d_evidence_bridge", "execution_bridge.py")
store_module = _load("lane_d_local_store_bridge", "local_store.py")

ExecutionEvidenceError = bridge.ExecutionEvidenceError
LocalEvidenceStoreError = store_module.LocalEvidenceStoreError
SECTIONS = bridge.SECTIONS


def _base_spec(**overrides: object) -> dict:
    spec = {
        "execution_id": "exec-bridge-neg-0001",
        "environment": "reference-fixture-lab",
        "correlation": {
            "campaign_id": "camp-1",
            "run_id": "run-1",
            "step_id": "step-1",
            "attempt_id": "attempt-1",
        },
        "classification": "sanitized",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:05Z",
        "status": "completed",
        "result": "inconclusive",
        "metadata": {"lab_profile": "reference"},
        "outputs": [
            {"section": "logs", "name": "runner.log", "role": "log", "media_type": "text/plain", "text": "ok\n"},
        ],
    }
    spec.update(overrides)
    return spec


def _emit(results_root: Path, **overrides: object) -> dict:
    return bridge.emit_from_spec(_base_spec(**overrides), results_root)


# ----------------------------------------------------------------- path safety


@pytest.mark.parametrize(
    "name",
    [
        "../escape.log",
        "logs/../../escape.log",
        "..",
        ".",
        "logs/..",
        "/abs/escape.log",
        "logs/./self.log",
        "logs/sub/../../escape.log",
        "a/../../../b.log",
    ],
)
def test_member_path_traversal_segments_rejected(name: str, tmp_path: Path) -> None:
    root = (tmp_path / "res" / "exec-x").resolve()
    root.mkdir(parents=True)
    with pytest.raises(ExecutionEvidenceError):
        bridge._safe_member_path(root, "logs", name)


def test_member_path_overly_deep_rejected(tmp_path: Path) -> None:
    root = (tmp_path / "res" / "exec-x").resolve()
    root.mkdir(parents=True)
    with pytest.raises(ExecutionEvidenceError):
        bridge._safe_member_path(root, "evidence", "a/b/c/d/e.log")


def test_member_path_null_byte_rejected(tmp_path: Path) -> None:
    root = (tmp_path / "res" / "exec-x").resolve()
    root.mkdir(parents=True)
    with pytest.raises(ExecutionEvidenceError):
        bridge._safe_member_path(root, "logs", "bad\x00.log")


def test_member_path_unsafe_characters_rejected(tmp_path: Path) -> None:
    root = (tmp_path / "res" / "exec-x").resolve()
    root.mkdir(parents=True)
    for name in ("space name.log", "semi;colon.log", "star*.log"):
        with pytest.raises(ExecutionEvidenceError):
            bridge._safe_member_path(root, "logs", name)


def test_member_path_symlink_target_rejected(tmp_path: Path) -> None:
    root = (tmp_path / "res" / "exec-x").resolve()
    (root / "logs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "logs" / "evil.log"
    link.symlink_to(outside)
    with pytest.raises(ExecutionEvidenceError):
        bridge._safe_member_path(root, "logs", "evil.log")


def test_emit_refuses_traversal_through_output_name(tmp_path: Path) -> None:
    spec = _base_spec(
        outputs=[{"section": "logs", "name": "../escape.log", "text": "x", "media_type": "text/plain"}]
    )
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(spec, tmp_path / "results")


# ----------------------------------------------------------------- id validation


@pytest.mark.parametrize("bad_id", ["", "has space", "slash/x", "colon:x", "unicøde", "../x"])
def test_invalid_execution_id_rejected(bad_id: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", execution_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "has space", "slash/x"])
def test_invalid_environment_or_correlation_id_rejected(bad_id: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", environment=bad_id)
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", correlation={"campaign_id": bad_id, "run_id": "r", "step_id": "s", "attempt_id": "a"})


def test_correlation_requires_all_four_ids(tmp_path: Path) -> None:
    for missing in ("campaign_id", "run_id", "step_id", "attempt_id"):
        partial = {"campaign_id": "c", "run_id": "r", "step_id": "s", "attempt_id": "a"}
        partial.pop(missing)
        with pytest.raises(ExecutionEvidenceError):
            _emit(tmp_path / "results", correlation=partial)


@pytest.mark.parametrize(
    "field,value",
    [
        ("started_at", "2026-01-01 00:00:00"),
        ("started_at", "2026-01-01T00:00:00"),
        ("started_at", "not-a-time"),
        ("ended_at", "2026-01-01T00:00:05"),
    ],
)
def test_non_rfc3339_utc_timestamp_rejected(field: str, value: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", **{field: value})


def test_ended_before_started_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", started_at="2026-01-01T00:00:10Z", ended_at="2026-01-01T00:00:05Z")


@pytest.mark.parametrize("bad_media", ["", "text", "text/", "/plain", "a" * 80 + "/b"])
def test_invalid_media_type_rejected(bad_media: str, tmp_path: Path) -> None:
    spec = _base_spec(
        outputs=[{"section": "logs", "name": "runner.log", "text": "x", "media_type": bad_media}]
    )
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(spec, tmp_path / "results")


# ------------------------------------------------------- enum / classification


@pytest.mark.parametrize("bad", ["", "done", "ERROR", "unknown"])
def test_invalid_status_rejected(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", status=bad)


@pytest.mark.parametrize("bad", ["", "broken", "UNKNOWN"])
def test_invalid_result_rejected(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", result=bad)


@pytest.mark.parametrize("bad", ["", "public", "secret-clearance"])
def test_invalid_classification_rejected(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", classification=bad)


# ----------------------------------------------------------- bounded metadata


def test_metadata_field_count_is_bounded(tmp_path: Path) -> None:
    metadata = {f"k{i}": i for i in range(bridge.MAX_METADATA_FIELDS + 1)}
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata=metadata)


def test_metadata_string_length_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata={"note": "x" * (bridge.MAX_METADATA_STRING + 1)})


def test_metadata_non_scalar_value_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata={"nested": {"bad": "value"}})


def test_metadata_invalid_key_chars_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata={"bad key": "value"})


@pytest.mark.parametrize("key", sorted(SECRET_KEYS))
def test_secret_or_raw_output_metadata_field_rejected(key: str, tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata={key: "synthetic-canary"})


def test_compound_metadata_key_with_secret_token_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata={"db_token_value": "synthetic-canary"})


def test_metadata_not_a_mapping_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", metadata=["not", "a", "mapping"])


# ---------------------------------------------------------- bounded references


def test_reference_count_exceeds_maximum_rejected(tmp_path: Path) -> None:
    outputs = [
        {"section": "artifacts", "name": f"a{i}.bin", "text": "x", "media_type": "application/octet-stream"}
        for i in range(bridge.MAX_REFS + 1)
    ]
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(_base_spec(outputs=outputs), tmp_path / "results")


def test_duplicate_reference_path_rejected(tmp_path: Path) -> None:
    outputs = [
        {"section": "logs", "name": "dup.log", "text": "one", "media_type": "text/plain"},
        {"section": "logs", "name": "dup.log", "text": "two", "media_type": "text/plain"},
    ]
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(_base_spec(outputs=outputs), tmp_path / "results")


def test_findings_payload_exceeds_maximum_rejected(tmp_path: Path) -> None:
    big = {"findings": [{"id": i, "note": "x" * 64} for i in range(200_000)]}
    with pytest.raises(ExecutionEvidenceError):
        _emit(tmp_path / "results", findings=big)


# ------------------------------------------------------- finalize / immutability


def test_emitter_refuses_writes_after_finalize(tmp_path: Path) -> None:
    emitter = bridge.ExecutionEvidenceEmitter(
        tmp_path / "results",
        execution_id="exec-final-001",
        environment="reference-fixture-lab",
        correlation={"campaign_id": "c", "run_id": "r", "step_id": "s", "attempt_id": "a"},
    )
    emitter.finalize(started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:00:05Z", status="completed", result="inconclusive")
    with pytest.raises(ExecutionEvidenceError):
        emitter.add_log("late.log", b"too late")
    with pytest.raises(ExecutionEvidenceError):
        emitter.finalize(started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:00:05Z", status="completed", result="inconclusive")


def test_identical_reemit_is_idempotent(tmp_path: Path) -> None:
    first = _emit(tmp_path / "results")
    second = _emit(tmp_path / "results")
    assert first["result_digest"] == second["result_digest"]


# --------------------------------------------------------- spec contract shape


def test_emit_rejects_unknown_spec_fields(tmp_path: Path) -> None:
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(_base_spec(unknown_field="nope"), tmp_path / "results")


def test_emit_rejects_output_with_both_source_and_text(tmp_path: Path) -> None:
    spec = _base_spec(outputs=[{"section": "logs", "name": "x.log", "text": "a", "source_path": "/etc/hostname"}])
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(spec, tmp_path / "results")


def test_emit_rejects_invalid_output_shape(tmp_path: Path) -> None:
    spec = _base_spec(outputs=[{"section": "logs", "name": "x.log", "unexpected": 1}])
    with pytest.raises(ExecutionEvidenceError):
        bridge.emit_from_spec(spec, tmp_path / "results")


# ------------------------------------------------------ large output referenced


def test_large_output_is_referenced_not_inlined(tmp_path: Path) -> None:
    payload = b"x" * (5 * 1024 * 1024)
    manifest = _emit(
        tmp_path / "results",
        outputs=[{"section": "evidence", "name": "big.bin", "role": "raw_output", "media_type": "application/octet-stream", "text": payload.decode()}],
    )
    ref = manifest["refs"]["evidence"][0]
    assert ref["size_bytes"] == len(payload)
    assert ref["sha256"] == bridge.sha256_hex(payload)
    assert "content" not in ref
    on_disk = (tmp_path / "results" / manifest["execution_id"] / ref["path"]).read_bytes()
    assert on_disk == payload


# ------------------------------------------------------------ deterministic digests


def test_result_digest_is_deterministic_across_runs(tmp_path: Path) -> None:
    first = _emit(tmp_path / "r1")["result_digest"]
    second = _emit(tmp_path / "r2")["result_digest"]
    assert first == second
    assert len(first) == 64


def test_result_digest_matches_canonical_recompute(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    body = {k: v for k, v in manifest.items() if k != "result_digest"}
    assert manifest["result_digest"] == bridge.sha256_hex(bridge.canonical_bytes(body))


# ---------------------------------------------------------- verification failure


def test_verify_fails_on_tampered_payload(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    ref = manifest["refs"]["logs"][0]
    target = tmp_path / "results" / manifest["execution_id"] / ref["path"]
    target.write_bytes(b"tampered content")
    report = bridge.verify_execution(tmp_path / "results", manifest["execution_id"])
    assert report["verified"] is False
    assert any("digest or size mismatch" in p for p in report["problems"])


def test_verify_fails_on_manifest_digest_tamper(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    path = tmp_path / "results" / manifest["execution_id"] / "manifest.json"
    tampered = dict(manifest)
    tampered["status"] = "failed"
    path.write_bytes(bridge.canonical_bytes(tampered))
    report = bridge.verify_execution(tmp_path / "results", manifest["execution_id"])
    assert report["verified"] is False
    assert any("result_digest mismatch" in p for p in report["problems"])


def test_verify_fails_on_missing_referenced_payload(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    ref = manifest["refs"]["logs"][0]
    (tmp_path / "results" / manifest["execution_id"] / ref["path"]).unlink()
    report = bridge.verify_execution(tmp_path / "results", manifest["execution_id"])
    assert report["verified"] is False


def test_verify_rejects_escaping_reference_path(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    # Craft a manifest whose reference escapes the execution root.
    escaped = dict(manifest)
    escaped["refs"] = dict(manifest["refs"])
    escaped["refs"]["logs"] = [dict(manifest["refs"]["logs"][0], path="../escape.log")]
    escaped.pop("result_digest", None)
    escaped["result_digest"] = bridge.sha256_hex(bridge.canonical_bytes(escaped))
    (tmp_path / "results" / manifest["execution_id"] / "manifest.json").write_bytes(bridge.canonical_bytes(escaped))
    report = bridge.verify_execution(tmp_path / "results", manifest["execution_id"])
    assert report["verified"] is False
    assert any("unsafe reference path" in p for p in report["problems"])


def test_load_manifest_rejects_identity_mismatch(tmp_path: Path) -> None:
    _emit(tmp_path / "results", execution_id="exec-real-1")
    with pytest.raises(ExecutionEvidenceError):
        bridge.load_manifest(tmp_path / "results", "exec-impostor-2")


# ------------------------------------------------------ projection / redaction


def test_project_execution_refuses_unverified_evidence(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    ref = manifest["refs"]["logs"][0]
    (tmp_path / "results" / manifest["execution_id"] / ref["path"]).write_bytes(b"tampered")
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(ExecutionEvidenceError):
        bridge.project_execution(store, tmp_path / "results", manifest["execution_id"])


def test_project_execution_derives_only_digest_only_summary_by_default(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    projection = bridge.project_execution(store, tmp_path / "results", manifest["execution_id"])
    assert store.verify(projection["summary_evidence_id"]) is True
    summary_record = store.get_record(projection["summary_evidence_id"])
    assert summary_record["classification"] == "summary"
    assert summary_record["redaction"]["removed_fields"] == ["refs", "metadata", "classification", "retention"]
    # Payload bytes are never projected unless explicitly requested.
    assert projection["payloads_projected"] is False
    assert projection["payload_evidence"] == []


def test_project_execution_payloads_stay_raw_and_non_exportable(tmp_path: Path) -> None:
    manifest = _emit(tmp_path / "results")
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    projection = bridge.project_execution(
        store, tmp_path / "results", manifest["execution_id"], include_payloads=True
    )
    assert projection["payloads_projected"] is True
    for entry in projection["payload_evidence"]:
        record = store.get_record(entry["evidence_id"])
        assert record["classification"] == "raw"
        with pytest.raises(LocalEvidenceStoreError):
            store.export_payload(entry["evidence_id"])
