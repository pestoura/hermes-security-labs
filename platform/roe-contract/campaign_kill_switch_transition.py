"""Deterministic campaign-state transition planning for the external kill switch.

This module is side-effect free. It evaluates the canonical RoE campaign lifecycle
policy and an external file-backed kill-switch source, then returns a content-addressed
transition assessment. It never mutates campaign state, dispatches cancellation,
authorizes execution, or creates an authorization reference.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = "1.0.0"
CAMPAIGN_STATES = (
    "DRAFT",
    "AUTHORIZED",
    "READY",
    "RUNNING",
    "PAUSED",
    "STOPPING",
    "STOPPED",
    "COMPLETED",
    "ABORTED",
    "EXPIRED",
)
_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


class CampaignKillSwitchTransitionError(ValueError):
    """Raised when planner inputs or the canonical policy are invalid."""


def _load_sibling(module_name: str) -> Any:
    existing = sys.modules.get(f"campaign_kill_switch_transition_{module_name}")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        f"campaign_kill_switch_transition_{module_name}",
        ROOT / f"{module_name}.py",
    )
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"campaign_kill_switch_transition_{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_kill_switch = _load_sibling("kill_switch")
KillSwitchError = _kill_switch.KillSwitchError
read_kill_switch = _kill_switch.read_kill_switch


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CampaignKillSwitchTransitionError(f"{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CampaignKillSwitchTransitionError(f"{field.upper()}_INVALID")
    return parsed.astimezone(timezone.utc)


def _load_policy(path: Path | None) -> dict[str, Any]:
    selected = path or ROOT / "intrusiveness-policy.yaml"
    try:
        data = yaml.safe_load(selected.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CampaignKillSwitchTransitionError("CAMPAIGN_POLICY_UNAVAILABLE") from exc
    if not isinstance(data, Mapping) or data.get("version") != "1.0.0":
        raise CampaignKillSwitchTransitionError("CAMPAIGN_POLICY_INVALID")

    transition = data.get("kill_switch_transition")
    terminal = data.get("terminal_states")
    active_campaign_state = data.get("active_campaign_state")
    if not isinstance(transition, Mapping):
        raise CampaignKillSwitchTransitionError("CAMPAIGN_POLICY_INVALID")
    sources = transition.get("from")
    target = transition.get("to")
    if (
        not isinstance(sources, list)
        or not sources
        or len(sources) != len(set(sources))
        or any(state not in CAMPAIGN_STATES for state in sources)
        or target not in CAMPAIGN_STATES
        or target in sources
        or not isinstance(terminal, list)
        or not terminal
        or len(terminal) != len(set(terminal))
        or any(state not in CAMPAIGN_STATES for state in terminal)
        or set(sources) & set(terminal)
        or target in terminal
        or active_campaign_state not in sources
    ):
        raise CampaignKillSwitchTransitionError("CAMPAIGN_POLICY_INVALID")
    return dict(data)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_result(result: Mapping[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "campaign-kill-switch-transition.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(
        result,
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def _result(
    *,
    campaign_id: str,
    evaluated_at: str,
    source_state: str,
    target_state: str,
    decision: str,
    codes: list[str],
    kill_switch_scope: str | None,
    kill_switch_campaign_id: str | None,
    fail_closed: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "evaluated_at": evaluated_at,
        "source_state": source_state,
        "target_state": target_state,
        "decision": decision,
        "codes": sorted(set(codes)),
        "kill_switch_scope": kill_switch_scope,
        "kill_switch_campaign_id": kill_switch_campaign_id,
        "fail_closed": fail_closed,
        "state_effect": (
            "RESTRICT_ONLY"
            if decision in {"TRANSITION_REQUIRED", "FAIL_CLOSED_TRANSITION_REQUIRED"}
            else "NONE"
        ),
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
    }
    result = {"transition_id": f"cks_{_digest(body)[:32]}", **body}
    _validate_result(result)
    return result


def plan_campaign_kill_switch_transition(
    *,
    kill_switch_path: Path | None,
    campaign_id: str,
    current_state: str,
    evaluated_at: str,
    policy_path: Path | None = None,
    released_state_max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Plan the restrictive campaign-state effect of the external kill switch.

    The canonical policy declares which active campaign states transition to
    ``STOPPING``. For those states, missing/invalid source state and stale/future
    release evidence fail closed into the same restrictive transition.

    Terminal, draft and already-stopping campaigns are never broadened or restarted.
    A valid campaign-scoped switch affects only its matching campaign.
    """

    if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
        raise CampaignKillSwitchTransitionError("CAMPAIGN_ID_INVALID")
    if current_state not in CAMPAIGN_STATES:
        raise CampaignKillSwitchTransitionError("CAMPAIGN_STATE_INVALID")
    if (
        not isinstance(released_state_max_age_seconds, int)
        or isinstance(released_state_max_age_seconds, bool)
        or not 1 <= released_state_max_age_seconds <= 3600
    ):
        raise CampaignKillSwitchTransitionError("RELEASE_FRESHNESS_POLICY_INVALID")

    now = _parse_time(evaluated_at, "evaluated_at")
    policy = _load_policy(policy_path)
    transition = policy["kill_switch_transition"]
    active_states = set(transition["from"])
    stopping_state = str(transition["to"])
    terminal_states = set(policy["terminal_states"])

    if current_state in terminal_states:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=current_state,
            decision="NO_TRANSITION_REQUIRED",
            codes=["CAMPAIGN_ALREADY_TERMINAL"],
            kill_switch_scope=None,
            kill_switch_campaign_id=None,
            fail_closed=False,
        )
    if current_state == stopping_state:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=current_state,
            decision="NO_TRANSITION_REQUIRED",
            codes=["CAMPAIGN_ALREADY_STOPPING"],
            kill_switch_scope=None,
            kill_switch_campaign_id=None,
            fail_closed=False,
        )
    if current_state not in active_states:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=current_state,
            decision="NO_TRANSITION_REQUIRED",
            codes=["CAMPAIGN_NOT_ACTIVE"],
            kill_switch_scope=None,
            kill_switch_campaign_id=None,
            fail_closed=False,
        )

    if kill_switch_path is None:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="FAIL_CLOSED_TRANSITION_REQUIRED",
            codes=["KILL_SWITCH_SOURCE_REQUIRED"],
            kill_switch_scope=None,
            kill_switch_campaign_id=None,
            fail_closed=True,
        )

    try:
        status = read_kill_switch(kill_switch_path)
    except KillSwitchError as exc:
        code = str(exc) or "KILL_SWITCH_UNTRUSTWORTHY"
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="FAIL_CLOSED_TRANSITION_REQUIRED",
            codes=[code],
            kill_switch_scope=None,
            kill_switch_campaign_id=None,
            fail_closed=True,
        )

    if status.engaged:
        if status.scope == "campaign" and status.campaign_id != campaign_id:
            return _result(
                campaign_id=campaign_id,
                evaluated_at=evaluated_at,
                source_state=current_state,
                target_state=current_state,
                decision="NO_TRANSITION_REQUIRED",
                codes=["KILL_SWITCH_OUT_OF_SCOPE"],
                kill_switch_scope=status.scope,
                kill_switch_campaign_id=status.campaign_id,
                fail_closed=False,
            )
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="TRANSITION_REQUIRED",
            codes=["KILL_SWITCH_ACTIVE"],
            kill_switch_scope=status.scope,
            kill_switch_campaign_id=status.campaign_id,
            fail_closed=False,
        )

    if status.updated_at is None:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="FAIL_CLOSED_TRANSITION_REQUIRED",
            codes=["KILL_SWITCH_RELEASE_TIMESTAMP_REQUIRED"],
            kill_switch_scope=status.scope,
            kill_switch_campaign_id=status.campaign_id,
            fail_closed=True,
        )

    updated_at = status.updated_at.astimezone(timezone.utc)
    if updated_at > now:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="FAIL_CLOSED_TRANSITION_REQUIRED",
            codes=["KILL_SWITCH_RELEASE_TIME_FUTURE"],
            kill_switch_scope=status.scope,
            kill_switch_campaign_id=status.campaign_id,
            fail_closed=True,
        )
    if (now - updated_at).total_seconds() > released_state_max_age_seconds:
        return _result(
            campaign_id=campaign_id,
            evaluated_at=evaluated_at,
            source_state=current_state,
            target_state=stopping_state,
            decision="FAIL_CLOSED_TRANSITION_REQUIRED",
            codes=["KILL_SWITCH_RELEASE_STALE"],
            kill_switch_scope=status.scope,
            kill_switch_campaign_id=status.campaign_id,
            fail_closed=True,
        )

    return _result(
        campaign_id=campaign_id,
        evaluated_at=evaluated_at,
        source_state=current_state,
        target_state=current_state,
        decision="NO_TRANSITION_REQUIRED",
        codes=["KILL_SWITCH_RELEASED_FRESH"],
        kill_switch_scope=status.scope,
        kill_switch_campaign_id=status.campaign_id,
        fail_closed=False,
    )
