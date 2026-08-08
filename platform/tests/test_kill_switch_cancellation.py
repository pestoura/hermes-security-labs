from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/gateway-protocol/kill_switch_cancellation.py"
SCHEMA_DIR = ROOT / "platform/gateway-protocol"

spec = importlib.util.spec_from_file_location("kill_switch_cancellation_contract", MODULE_PATH)
assert spec and spec.loader
ksc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ksc
spec.loader.exec_module(ksc)

CAMPAIGN_A = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
CAMPAIGN_B = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
RUN_A = str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
RUN_B = str(uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
STEP_A = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
STEP_B = str(uuid.UUID("44444444-4444-4444-8444-444444444444"))
ATTEMPT_A = str(uuid.UUID("55555555-5555-4555-8555-555555555555"))
ATTEMPT_B = str(uuid.UUID("66666666-6666-4666-8666-666666666666"))
NOW = "2026-08-08T02:15:00Z"


def attempt(
    *, campaign_id: str = CAMPAIGN_A, run_id: str = RUN_A, step_id: str = STEP_A,
    attempt_id: str = ATTEMPT_A, state: str = "running",
    cancellation_mode: str = "cooperative_then_force", grace_period_ms: int = 5000,
) -> dict:
    return {
        "correlation": {
            "campaign_id": campaign_id,
            "run_id": run_id,
            "step_id": step_id,
            "attempt_id": attempt_id,
        },
        "state": state,
        "cancellation_mode": cancellation_mode,
        "grace_period_ms": grace_period_ms,
    }


def inventory(*attempts: dict) -> dict:
    return ksc.build_active_attempt_inventory(
        attempts=list(attempts), generated_at="2026-08-08T02:14:55Z"
    )


def write_switch(
    path: Path,
    *,
    state: str,
    scope: str = "global",
    campaign_id=None,
    updated_at="2026-08-08T02:14:50Z",
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "state": state,
                "scope": scope,
                "campaign_id": campaign_id,
                "updated_at": updated_at,
            }
        ),
        encoding="utf-8",
    )
    return path


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_inventory_and_global_cancellation_plan_validate_against_schemas(tmp_path: Path) -> None:
    inv = inventory(
        attempt(),
        attempt(campaign_id=CAMPAIGN_B, run_id=RUN_B, step_id=STEP_B, attempt_id=ATTEMPT_B),
    )
    switch = write_switch(tmp_path / "kill.json", state="engaged")
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW
    )
    jsonschema.validate(inv, load_schema("active-attempt-inventory.schema.json"))
    jsonschema.validate(plan, load_schema("kill-switch-cancellation-plan.schema.json"))
    assert plan["decision"] == "CANCEL_REQUIRED"
    assert len(plan["cancellation_requests"]) == 2
    assert plan["codes"] == ["KILL_SWITCH_ACTIVE"]
    assert all(message["message_type"] == "runner.cancellation.request" for message in plan["cancellation_requests"])
    assert all(message["reason"] == "policy" for message in plan["cancellation_requests"])
    assert all(message["requested_by"] == "gateway" for message in plan["cancellation_requests"])


def test_campaign_switch_only_cancels_matching_campaign(tmp_path: Path) -> None:
    inv = inventory(
        attempt(),
        attempt(campaign_id=CAMPAIGN_B, run_id=RUN_B, step_id=STEP_B, attempt_id=ATTEMPT_B),
    )
    switch = write_switch(
        tmp_path / "kill.json", state="engaged", scope="campaign", campaign_id=CAMPAIGN_A
    )
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW
    )
    assert [item["correlation"]["campaign_id"] for item in plan["cancellation_requests"]] == [CAMPAIGN_A]
    assert len(plan["unaffected_attempt_refs"]) == 1
    assert plan["fail_closed"] is False


def test_already_cancelling_attempt_is_not_duplicated(tmp_path: Path) -> None:
    inv = inventory(
        attempt(state="cancelling"),
        attempt(attempt_id=ATTEMPT_B, step_id=STEP_B, state="running"),
    )
    switch = write_switch(tmp_path / "kill.json", state="engaged")
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW
    )
    assert len(plan["cancellation_requests"]) == 1
    assert len(plan["already_cancelling_attempt_refs"]) == 1
    assert plan["decision"] == "CANCEL_REQUIRED"


def test_fresh_released_switch_does_not_cancel(tmp_path: Path) -> None:
    inv = inventory(attempt())
    switch = write_switch(tmp_path / "kill.json", state="released")
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW,
        released_state_max_age_seconds=60,
    )
    assert plan["decision"] == "NO_CANCELLATION_REQUIRED"
    assert plan["codes"] == ["KILL_SWITCH_RELEASED_FRESH"]
    assert plan["cancellation_requests"] == []
    assert len(plan["unaffected_attempt_refs"]) == 1


@pytest.mark.parametrize(
    ("updated_at", "expected_code"),
    [
        (None, "KILL_SWITCH_RELEASE_TIMESTAMP_REQUIRED"),
        ("2026-08-08T02:16:00Z", "KILL_SWITCH_RELEASE_TIME_FUTURE"),
        ("2026-08-08T01:00:00Z", "KILL_SWITCH_RELEASE_STALE"),
    ],
)
def test_untrusted_released_state_fails_closed_and_cancels_all(
    tmp_path: Path, updated_at: str | None, expected_code: str
) -> None:
    inv = inventory(
        attempt(),
        attempt(campaign_id=CAMPAIGN_B, run_id=RUN_B, step_id=STEP_B, attempt_id=ATTEMPT_B),
    )
    switch = write_switch(
        tmp_path / "kill.json", state="released", updated_at=updated_at
    )
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW,
        released_state_max_age_seconds=60,
    )
    assert plan["fail_closed"] is True
    assert plan["decision"] == "CANCEL_REQUIRED"
    assert expected_code in plan["codes"]
    assert len(plan["cancellation_requests"]) == 2


def test_missing_or_invalid_switch_source_fails_closed(tmp_path: Path) -> None:
    inv = inventory(attempt())
    missing = ksc.plan_kill_switch_cancellations(
        kill_switch_path=None, inventory=inv, emitted_at=NOW
    )
    assert missing["fail_closed"] is True
    assert missing["codes"] == ["KILL_SWITCH_SOURCE_REQUIRED"]
    assert len(missing["cancellation_requests"]) == 1

    broken_path = tmp_path / "broken.json"
    broken_path.write_text("not-json", encoding="utf-8")
    broken = ksc.plan_kill_switch_cancellations(
        kill_switch_path=broken_path, inventory=inv, emitted_at=NOW
    )
    assert broken["fail_closed"] is True
    assert broken["codes"] == ["KILL_SWITCH_INVALID"]
    assert len(broken["cancellation_requests"]) == 1


def test_non_uuid_campaign_switch_cannot_silently_miss_active_runner_attempts(tmp_path: Path) -> None:
    inv = inventory(attempt())
    switch = write_switch(
        tmp_path / "kill.json", state="engaged", scope="campaign", campaign_id="legacy-campaign-id"
    )
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW
    )
    assert plan["fail_closed"] is True
    assert "KILL_SWITCH_CAMPAIGN_CORRELATION_INVALID" in plan["codes"]
    assert len(plan["cancellation_requests"]) == 1


def test_inventory_tampering_and_forbidden_fields_fail_closed() -> None:
    inv = inventory(attempt())
    tampered = deepcopy(inv)
    tampered["attempts"][0]["state"] = "accepted"
    with pytest.raises(ksc.KillSwitchCancellationError, match="canonical content"):
        ksc.plan_kill_switch_cancellations(
            kill_switch_path=None, inventory=tampered, emitted_at=NOW
        )

    with pytest.raises(ksc.KillSwitchCancellationError, match="target, execution"):
        ksc.build_active_attempt_inventory(
            attempts=[{**attempt(), "target": "forbidden"}],
            generated_at="2026-08-08T02:14:55Z",
        )


def test_plan_is_restrict_only_and_never_dispatches_or_authorizes(tmp_path: Path) -> None:
    inv = inventory(attempt())
    switch = write_switch(tmp_path / "kill.json", state="engaged")
    plan = ksc.plan_kill_switch_cancellations(
        kill_switch_path=switch, inventory=inv, emitted_at=NOW
    )
    assert plan["dispatch_performed"] is False
    assert plan["safety_effect"] == "RESTRICT_ONLY"
    assert plan["authorization_effect"] == "NONE"
    assert plan["execution_authority"] == "NONE"
    assert "CANCELLATION_MESSAGES_BUILT_NOT_DISPATCHED" in plan["limitations"]
    encoded = json.dumps(plan, sort_keys=True).lower()
    for forbidden in ("target", "command", "credential", "secret", "authorization_ref"):
        assert f'"{forbidden}"' not in encoded
