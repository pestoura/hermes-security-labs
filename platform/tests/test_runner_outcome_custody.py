from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CUSTODY_PATH = ROOT / "platform" / "evidence-plane" / "runner_outcome_custody.py"
STORE_PATH = ROOT / "platform" / "evidence-plane" / "local_store.py"
POLICY_PATH = ROOT / "platform" / "evidence-plane" / "runner-outcome-policy.yaml"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


custody_module = _load("runner_outcome_custody_test", CUSTODY_PATH)
store_module = _load("runner_outcome_custody_store_test", STORE_PATH)

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
FIRST_ATTEMPT = "44444444-4444-4444-8444-444444444444"
RETRY_ATTEMPT = "55555555-5555-4555-8555-555555555555"


class FailingStore:
    def __init__(self) -> None:
        self.calls = 0

    def put(self, record: dict[str, Any], payload: bytes) -> str:
        del record, payload
        self.calls += 1
        raise OSError("simulated evidence store outage")


def _enabled_policy() -> dict[str, Any]:
    policy = custody_module.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return policy


def _request(*, attempt_id: str = FIRST_ATTEMPT) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": attempt_id,
        },
        "emitted_at": "2026-08-09T19:00:00Z",
        "authorization_ref": "tb1-authz:v1:" + ("1" * 64),
        "idempotency_key": "fixture-custody-key-one",
        "operation": {
            "capability_id": "web.discovery.headers",
            "input": {
                "operation_id": "web.discovery.headers",
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "webgoat-web"},
                "parameters": {},
            },
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
        },
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 0},
    }


def _outcome(*, attempt_id: str = FIRST_ATTEMPT, status: str = "PASS") -> dict[str, Any]:
    output = {
        "adapter_id": "webgoat-l1",
        "target_id": "webgoat-web",
        "environment_id": "webgoat",
        "capability_id": "web.discovery.headers",
        "http_status": 200,
        "headers": [{"name": "server", "value": "WebGoat"}],
        "redirects_followed": False,
    }
    digest = custody_module.execution_bridge.sha256_hex(
        custody_module.execution_bridge.canonical_bytes(output)
    )
    return {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": attempt_id,
        },
        "emitted_at": "2026-08-09T19:00:01Z",
        "status": status,
        "started_at": "2026-08-09T19:00:00Z",
        "finished_at": "2026-08-09T19:00:01Z",
        "output": output,
        "evidence_refs": [
            {
                "evidence_id": str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
                "kind": "execution",
                "classification": "INTERNAL",
                "sha256": digest,
            }
        ],
    }


def _custody() -> Any:
    return custody_module.RunnerOutcomeCustody(_enabled_policy())


def test_committed_policy_is_disabled_fail_closed() -> None:
    policy = custody_module.load_policy(POLICY_PATH)
    assert custody_module.validate_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["custody"]["evidence_plane_projection"] == "required"
    assert policy["custody"]["include_payloads_in_projection"] is False


def test_cli_validates_committed_policy() -> None:
    assert custody_module.main(["validate"]) == 0


def test_disabled_policy_refuses_without_creating_execution(tmp_path: Path) -> None:
    custody = custody_module.RunnerOutcomeCustody(custody_module.load_policy(POLICY_PATH))
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(custody_module.RunnerOutcomeCustodyError) as exc:
        custody.persist(
            request=_request(), outcome=_outcome(), adapter_id="webgoat-l1",
            principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
            evidence_store=store,
        )
    assert exc.value.code == "CUSTODY_DISABLED"
    assert not (tmp_path / "results").exists()


def test_pass_outcome_persists_and_projects_without_security_overclaim(tmp_path: Path) -> None:
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    result = _custody().persist(
        request=_request(), outcome=_outcome(), adapter_id="webgoat-l1",
        principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
        evidence_store=store,
    )
    verified = custody_module.execution_bridge.verify_execution(tmp_path / "results", result.execution_id)
    assert verified["verified"] is True
    manifest = custody_module.execution_bridge.load_manifest(tmp_path / "results", result.execution_id)
    assert manifest["status"] == "completed"
    assert manifest["result"] == "inconclusive"
    assert manifest["metadata"]["runner_status"] == "PASS"
    assert manifest["metadata"]["source_attempt_id"] == FIRST_ATTEMPT
    assert manifest["target"] == "webgoat-web"
    assert store.verify(result.manifest_evidence_id) is True
    assert store.verify(result.summary_evidence_id) is True
    assert result.replayed_custody is False
    assert store.get_record(result.manifest_evidence_id)["classification"] == "restricted"
    assert store.get_record(result.summary_evidence_id)["classification"] == "summary"


def test_same_outcome_reemission_is_idempotent(tmp_path: Path) -> None:
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    custody = _custody()
    kwargs = dict(
        request=_request(), outcome=_outcome(), adapter_id="webgoat-l1",
        principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
        evidence_store=store,
    )
    first = custody.persist(**kwargs)
    second = custody.persist(**kwargs)
    assert second.execution_id == first.execution_id
    assert second.result_digest == first.result_digest
    assert second.manifest_evidence_id == first.manifest_evidence_id
    assert second.summary_evidence_id == first.summary_evidence_id
    assert second.replayed_custody is True


def test_exact_retry_new_attempt_addresses_original_custody_record(tmp_path: Path) -> None:
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    custody = _custody()
    original_outcome = _outcome(attempt_id=FIRST_ATTEMPT)
    first = custody.persist(
        request=_request(attempt_id=FIRST_ATTEMPT), outcome=original_outcome,
        adapter_id="webgoat-l1", principal_id="hexor.execution-gateway",
        results_root=tmp_path / "results", evidence_store=store,
    )
    retry = custody.persist(
        request=_request(attempt_id=RETRY_ATTEMPT), outcome=original_outcome,
        adapter_id="webgoat-l1", principal_id="hexor.execution-gateway",
        results_root=tmp_path / "results", evidence_store=store,
    )
    assert retry.execution_id == first.execution_id
    assert retry.result_digest == first.result_digest
    assert retry.replayed_custody is True
    verified = custody_module.execution_bridge.verify_execution(tmp_path / "results", retry.execution_id)
    assert verified["verified"] is True
    replayed_manifest = custody_module.execution_bridge.load_manifest(tmp_path / "results", retry.execution_id)
    assert replayed_manifest["correlation"]["attempt_id"] == FIRST_ATTEMPT


def test_output_digest_mismatch_is_refused_before_write(tmp_path: Path) -> None:
    outcome = _outcome()
    outcome["output"]["http_status"] = 418
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(custody_module.RunnerOutcomeCustodyError) as exc:
        _custody().persist(
            request=_request(), outcome=outcome, adapter_id="webgoat-l1",
            principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
            evidence_store=store,
        )
    assert exc.value.code == "OUTCOME_EVIDENCE_DIGEST_MISMATCH"
    assert not (tmp_path / "results").exists()


def test_logical_correlation_mismatch_is_refused(tmp_path: Path) -> None:
    outcome = _outcome()
    outcome["correlation"]["run_id"] = "66666666-6666-4666-8666-666666666666"
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(custody_module.RunnerOutcomeCustodyError) as exc:
        _custody().persist(
            request=_request(), outcome=outcome, adapter_id="webgoat-l1",
            principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
            evidence_store=store,
        )
    assert exc.value.code == "OUTCOME_CORRELATION_MISMATCH"


def test_projection_failure_preserves_execution_for_custody_only_retry(tmp_path: Path) -> None:
    custody = _custody()
    request = _request()
    outcome = _outcome()
    failing = FailingStore()
    with pytest.raises(custody_module.RunnerOutcomeCustodyError) as exc:
        custody.persist(
            request=request, outcome=outcome, adapter_id="webgoat-l1",
            principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
            evidence_store=failing,
        )
    assert exc.value.code == "EVIDENCE_PROJECTION_FAILED"
    execution_id, _ = custody_module._execution_id("webgoat-l1", request)
    assert custody_module.execution_bridge.verify_execution(tmp_path / "results", execution_id)["verified"] is True
    healthy = store_module.LocalEvidenceStore(tmp_path / "healthy-store")
    recovered = custody.persist(
        request=request, outcome=outcome, adapter_id="webgoat-l1",
        principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
        evidence_store=healthy,
    )
    assert recovered.execution_id == execution_id
    assert recovered.replayed_custody is True
    assert healthy.verify(recovered.manifest_evidence_id)
    assert healthy.verify(recovered.summary_evidence_id)


def test_existing_execution_with_divergent_terminal_outcome_is_refused(tmp_path: Path) -> None:
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    custody = _custody()
    request = _request()
    custody.persist(
        request=request, outcome=_outcome(), adapter_id="webgoat-l1",
        principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
        evidence_store=store,
    )
    changed = _outcome()
    changed["output"]["http_status"] = 204
    changed["evidence_refs"][0]["sha256"] = custody_module.execution_bridge.sha256_hex(
        custody_module.execution_bridge.canonical_bytes(changed["output"])
    )
    with pytest.raises(
        (custody_module.RunnerOutcomeCustodyError, custody_module.execution_bridge.ExecutionEvidenceError)
    ):
        custody.persist(
            request=request, outcome=changed, adapter_id="webgoat-l1",
            principal_id="hexor.execution-gateway", results_root=tmp_path / "results",
            evidence_store=store,
        )


def test_runner_status_mapping_does_not_assert_security_conclusion() -> None:
    assert custody_module.RUNNER_STATUS_MAP["PASS"] == ("completed", "inconclusive")
    assert custody_module.RUNNER_STATUS_MAP["FAIL"] == ("completed", "inconclusive")
    assert custody_module.RUNNER_STATUS_MAP["ERROR"] == ("failed", "error")
    assert custody_module.RUNNER_STATUS_MAP["REFUSED"] == ("completed", "skipped")


def test_projection_policy_cannot_enable_payloads_in_this_lane() -> None:
    policy = _enabled_policy()
    policy["custody"]["include_payloads_in_projection"] = True
    assert any("payload projection must remain disabled" in item for item in custody_module.validate_policy(policy))


def test_custody_never_claims_execution_authority() -> None:
    policy = _enabled_policy()
    policy["execution_authority"] = "evidence-plane"
    assert any("never claim execution authority" in item for item in custody_module.validate_policy(policy))
