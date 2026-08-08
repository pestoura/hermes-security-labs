from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ROE = ROOT / "platform/roe-contract"
CAMPAIGN_ID = "campaign:a02:transition"
OTHER_CAMPAIGN_ID = "campaign:a02:other"
EVALUATED_AT = "2026-08-08T12:00:00Z"
ACTIVE_STATES = ("AUTHORIZED", "READY", "RUNNING", "PAUSED")
TERMINAL_STATES = ("STOPPED", "COMPLETED", "ABORTED", "EXPIRED")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


transition = load_module(
    "svp2_a02_campaign_kill_switch_transition",
    ROE / "campaign_kill_switch_transition.py",
)


def write_switch(
    path: Path,
    *,
    state: str,
    scope: str = "global",
    campaign_id: str | None = None,
    updated_at: str | None = "2026-08-08T11:59:00Z",
) -> Path:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "state": state,
        "scope": scope,
    }
    if campaign_id is not None:
        payload["campaign_id"] = campaign_id
    if updated_at is not None:
        payload["updated_at"] = updated_at
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("current_state", ACTIVE_STATES)
def test_global_engaged_switch_transitions_every_policy_active_state_to_stopping(
    tmp_path: Path,
    current_state: str,
) -> None:
    result = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=write_switch(tmp_path / "switch.json", state="engaged"),
        campaign_id=CAMPAIGN_ID,
        current_state=current_state,
        evaluated_at=EVALUATED_AT,
    )

    assert result["source_state"] == current_state
    assert result["target_state"] == "STOPPING"
    assert result["decision"] == "TRANSITION_REQUIRED"
    assert result["codes"] == ["KILL_SWITCH_ACTIVE"]
    assert result["kill_switch_scope"] == "global"
    assert result["kill_switch_campaign_id"] is None
    assert result["fail_closed"] is False
    assert result["state_effect"] == "RESTRICT_ONLY"
    assert result["authorization_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"


def test_matching_campaign_switch_transitions_and_nonmatching_switch_does_not(
    tmp_path: Path,
) -> None:
    matching = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=write_switch(
            tmp_path / "matching.json",
            state="engaged",
            scope="campaign",
            campaign_id=CAMPAIGN_ID,
        ),
        campaign_id=CAMPAIGN_ID,
        current_state="READY",
        evaluated_at=EVALUATED_AT,
    )
    other = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=write_switch(
            tmp_path / "other.json",
            state="engaged",
            scope="campaign",
            campaign_id=OTHER_CAMPAIGN_ID,
        ),
        campaign_id=CAMPAIGN_ID,
        current_state="READY",
        evaluated_at=EVALUATED_AT,
    )

    assert matching["decision"] == "TRANSITION_REQUIRED"
    assert matching["target_state"] == "STOPPING"
    assert matching["kill_switch_campaign_id"] == CAMPAIGN_ID
    assert other["decision"] == "NO_TRANSITION_REQUIRED"
    assert other["target_state"] == "READY"
    assert other["codes"] == ["KILL_SWITCH_OUT_OF_SCOPE"]
    assert other["state_effect"] == "NONE"


@pytest.mark.parametrize("current_state", ACTIVE_STATES)
def test_missing_source_fails_closed_for_every_active_state(
    current_state: str,
) -> None:
    result = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=None,
        campaign_id=CAMPAIGN_ID,
        current_state=current_state,
        evaluated_at=EVALUATED_AT,
    )

    assert result["decision"] == "FAIL_CLOSED_TRANSITION_REQUIRED"
    assert result["target_state"] == "STOPPING"
    assert result["codes"] == ["KILL_SWITCH_SOURCE_REQUIRED"]
    assert result["fail_closed"] is True
    assert result["state_effect"] == "RESTRICT_ONLY"


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ("not-json", "KILL_SWITCH_INVALID"),
        ('{"schema_version":"9.9.9","state":"released"}', "KILL_SWITCH_SCHEMA_UNSUPPORTED"),
    ],
)
def test_invalid_source_fails_closed_for_active_campaign(
    tmp_path: Path,
    raw: str,
    expected_code: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(raw, encoding="utf-8")

    result = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=path,
        campaign_id=CAMPAIGN_ID,
        current_state="RUNNING",
        evaluated_at=EVALUATED_AT,
    )

    assert result["decision"] == "FAIL_CLOSED_TRANSITION_REQUIRED"
    assert result["target_state"] == "STOPPING"
    assert result["codes"] == [expected_code]
    assert result["fail_closed"] is True


@pytest.mark.parametrize(
    ("updated_at", "expected_code"),
    [
        (None, "KILL_SWITCH_RELEASE_TIMESTAMP_REQUIRED"),
        ("2026-08-08T12:00:01Z", "KILL_SWITCH_RELEASE_TIME_FUTURE"),
        ("2026-08-08T11:50:00Z", "KILL_SWITCH_RELEASE_STALE"),
    ],
)
def test_untrustworthy_release_evidence_fails_closed(
    tmp_path: Path,
    updated_at: str | None,
    expected_code: str,
) -> None:
    result = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=write_switch(
            tmp_path / f"released-{expected_code}.json",
            state="released",
            updated_at=updated_at,
        ),
        campaign_id=CAMPAIGN_ID,
        current_state="PAUSED",
        evaluated_at=EVALUATED_AT,
        released_state_max_age_seconds=300,
    )

    assert result["decision"] == "FAIL_CLOSED_TRANSITION_REQUIRED"
    assert result["target_state"] == "STOPPING"
    assert result["codes"] == [expected_code]
    assert result["fail_closed"] is True


def test_fresh_release_preserves_active_state_without_broadening_authority(
    tmp_path: Path,
) -> None:
    result = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=write_switch(
            tmp_path / "released.json",
            state="released",
            updated_at="2026-08-08T11:59:00Z",
        ),
        campaign_id=CAMPAIGN_ID,
        current_state="RUNNING",
        evaluated_at=EVALUATED_AT,
        released_state_max_age_seconds=300,
    )

    assert result["decision"] == "NO_TRANSITION_REQUIRED"
    assert result["source_state"] == result["target_state"] == "RUNNING"
    assert result["codes"] == ["KILL_SWITCH_RELEASED_FRESH"]
    assert result["fail_closed"] is False
    assert result["state_effect"] == "NONE"
    assert result["authorization_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"


def test_inactive_stopping_and_terminal_states_are_never_restarted_or_broadened(
    tmp_path: Path,
) -> None:
    invalid_source = tmp_path / "invalid-source.json"
    invalid_source.write_text("not-json", encoding="utf-8")

    draft = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=invalid_source,
        campaign_id=CAMPAIGN_ID,
        current_state="DRAFT",
        evaluated_at=EVALUATED_AT,
    )
    stopping = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=invalid_source,
        campaign_id=CAMPAIGN_ID,
        current_state="STOPPING",
        evaluated_at=EVALUATED_AT,
    )

    assert draft["decision"] == "NO_TRANSITION_REQUIRED"
    assert draft["target_state"] == "DRAFT"
    assert draft["codes"] == ["CAMPAIGN_NOT_ACTIVE"]
    assert stopping["decision"] == "NO_TRANSITION_REQUIRED"
    assert stopping["target_state"] == "STOPPING"
    assert stopping["codes"] == ["CAMPAIGN_ALREADY_STOPPING"]

    for terminal_state in TERMINAL_STATES:
        terminal = transition.plan_campaign_kill_switch_transition(
            kill_switch_path=invalid_source,
            campaign_id=CAMPAIGN_ID,
            current_state=terminal_state,
            evaluated_at=EVALUATED_AT,
        )
        assert terminal["decision"] == "NO_TRANSITION_REQUIRED"
        assert terminal["target_state"] == terminal_state
        assert terminal["codes"] == ["CAMPAIGN_ALREADY_TERMINAL"]
        assert terminal["state_effect"] == "NONE"


def test_transition_id_is_content_addressed_and_deterministic(tmp_path: Path) -> None:
    switch = write_switch(tmp_path / "switch.json", state="engaged")
    first = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=switch,
        campaign_id=CAMPAIGN_ID,
        current_state="AUTHORIZED",
        evaluated_at=EVALUATED_AT,
    )
    second = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=switch,
        campaign_id=CAMPAIGN_ID,
        current_state="AUTHORIZED",
        evaluated_at=EVALUATED_AT,
    )
    changed = transition.plan_campaign_kill_switch_transition(
        kill_switch_path=switch,
        campaign_id=CAMPAIGN_ID,
        current_state="READY",
        evaluated_at=EVALUATED_AT,
    )

    assert first == second
    assert first["transition_id"].startswith("cks_")
    assert len(first["transition_id"]) == 36
    assert changed["transition_id"] != first["transition_id"]


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        ({"campaign_id": "x"}, "CAMPAIGN_ID_INVALID"),
        ({"current_state": "UNKNOWN"}, "CAMPAIGN_STATE_INVALID"),
        ({"evaluated_at": "not-a-time"}, "EVALUATED_AT_INVALID"),
        ({"released_state_max_age_seconds": 0}, "RELEASE_FRESHNESS_POLICY_INVALID"),
        ({"released_state_max_age_seconds": True}, "RELEASE_FRESHNESS_POLICY_INVALID"),
    ],
)
def test_invalid_planner_inputs_are_refused(
    kwargs: dict[str, object],
    expected_code: str,
) -> None:
    parameters: dict[str, object] = {
        "kill_switch_path": None,
        "campaign_id": CAMPAIGN_ID,
        "current_state": "RUNNING",
        "evaluated_at": EVALUATED_AT,
    }
    parameters.update(kwargs)

    with pytest.raises(transition.CampaignKillSwitchTransitionError) as exc:
        transition.plan_campaign_kill_switch_transition(**parameters)

    assert str(exc.value) == expected_code


def test_invalid_policy_is_refused(tmp_path: Path) -> None:
    bad_policy = tmp_path / "policy.yaml"
    bad_policy.write_text(
        """version: 1.0.0
levels: {}
active_campaign_state: RUNNING
kill_switch_transition:
  from: [RUNNING]
  to: COMPLETED
terminal_states: [COMPLETED]
""",
        encoding="utf-8",
    )

    with pytest.raises(transition.CampaignKillSwitchTransitionError) as exc:
        transition.plan_campaign_kill_switch_transition(
            kill_switch_path=None,
            campaign_id=CAMPAIGN_ID,
            current_state="RUNNING",
            evaluated_at=EVALUATED_AT,
            policy_path=bad_policy,
        )

    assert str(exc.value) == "CAMPAIGN_POLICY_INVALID"
