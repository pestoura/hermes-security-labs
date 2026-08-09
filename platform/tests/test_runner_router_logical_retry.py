from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = ROOT / "platform" / "runner-dispatch" / "router.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "runner_router_logical_retry_test",
        ROUTER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


router = _load()

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
FIRST_ATTEMPT = "44444444-4444-4444-8444-444444444444"
RETRY_ATTEMPT = "55555555-5555-4555-8555-555555555555"


def _correlation(attempt_id: str, *, run_id: str = RUN_ID) -> dict[str, str]:
    return {
        "campaign_id": CAMPAIGN_ID,
        "run_id": run_id,
        "step_id": STEP_ID,
        "attempt_id": attempt_id,
    }


def _outcome(correlation: dict[str, str]) -> dict:
    return {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-09T19:00:01Z",
        "status": "PASS",
        "started_at": "2026-08-09T19:00:00Z",
        "finished_at": "2026-08-09T19:00:01Z",
        "output": {"adapter_id": "fixture-runner"},
        "evidence_refs": [
            {
                "evidence_id": str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
                "kind": "execution",
                "classification": "INTERNAL",
                "sha256": "a" * 64,
            }
        ],
    }


def test_exact_retry_accepts_original_effect_attempt_correlation() -> None:
    expected_retry = _correlation(RETRY_ATTEMPT)
    original_outcome = _outcome(_correlation(FIRST_ATTEMPT))

    messages = router._validate_adapter_result(
        {"messages": [original_outcome]},
        correlation=expected_retry,
    )

    assert messages == (original_outcome,)
    assert messages[0]["correlation"]["attempt_id"] == FIRST_ATTEMPT
    assert expected_retry["attempt_id"] == RETRY_ATTEMPT


def test_same_attempt_correlation_still_passes() -> None:
    correlation = _correlation(FIRST_ATTEMPT)
    outcome = _outcome(correlation)
    assert router._validate_adapter_result(
        {"messages": [outcome]},
        correlation=correlation,
    ) == (outcome,)


def test_different_logical_run_is_refused_even_if_attempt_is_valid() -> None:
    expected = _correlation(RETRY_ATTEMPT)
    wrong_run = _outcome(
        _correlation(
            FIRST_ATTEMPT,
            run_id="66666666-6666-4666-8666-666666666666",
        )
    )

    with pytest.raises(router.DispatchRouterError) as exc:
        router._validate_adapter_result(
            {"messages": [wrong_run]},
            correlation=expected,
        )
    assert exc.value.code == "ADAPTER_CORRELATION_MISMATCH"


def test_missing_attempt_id_is_not_accepted_as_logical_replay() -> None:
    expected = _correlation(RETRY_ATTEMPT)
    actual = _correlation(FIRST_ATTEMPT)
    actual.pop("attempt_id")
    assert router._logical_correlation_matches(actual, expected) is False
