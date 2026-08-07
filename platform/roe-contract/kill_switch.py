"""External file-backed kill switch for Rules of Engagement authorization.

The kill switch is deliberately *external* to the step request: an operator
must be able to halt execution without cooperation from the requesting
component. The switch is a small JSON document on disk whose engaged state
blocks every authorization decision.

Fail-closed contract: when a kill-switch source is configured but the file is
missing, unreadable, malformed, of an unsupported schema or carries an
unparsable state, authorization is refused. Absence of evidence is never
treated as "not engaged". Only an explicitly configured *and* valid document
declaring ``state: released`` permits execution to proceed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
ENGAGED = "engaged"
RELEASED = "released"
STATES = (ENGAGED, RELEASED)

_FORBIDDEN_FIELDS = {"token", "secret", "password", "private_key", "api_key"}


class KillSwitchError(ValueError):
    """Raised with a stable decision code when the kill switch is untrustworthy."""


@dataclass(frozen=True)
class KillSwitchStatus:
    engaged: bool
    scope: str
    reason_code: str | None
    updated_at: datetime | None
    campaign_id: str | None


def _parse_datetime(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise KillSwitchError("KILL_SWITCH_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KillSwitchError("KILL_SWITCH_INVALID")
    return parsed


def read_kill_switch(path: Path) -> KillSwitchStatus:
    """Read and validate the kill-switch document, fail-closed on any defect."""

    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise KillSwitchError("KILL_SWITCH_UNAVAILABLE") from exc

    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise KillSwitchError("KILL_SWITCH_INVALID") from exc

    if not isinstance(document, Mapping):
        raise KillSwitchError("KILL_SWITCH_INVALID")
    for key in document:
        if str(key).lower() in _FORBIDDEN_FIELDS:
            raise KillSwitchError("KILL_SWITCH_INVALID")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise KillSwitchError("KILL_SWITCH_SCHEMA_UNSUPPORTED")

    state = document.get("state")
    if state not in STATES:
        raise KillSwitchError("KILL_SWITCH_INVALID")

    scope = document.get("scope", "global")
    if scope not in {"global", "campaign"}:
        raise KillSwitchError("KILL_SWITCH_INVALID")

    campaign_id = document.get("campaign_id")
    if scope == "campaign":
        if not isinstance(campaign_id, str) or not campaign_id.strip():
            raise KillSwitchError("KILL_SWITCH_INVALID")
    elif campaign_id is not None and not isinstance(campaign_id, str):
        raise KillSwitchError("KILL_SWITCH_INVALID")

    reason_code = document.get("reason_code")
    if reason_code is not None and (
        not isinstance(reason_code, str) or len(reason_code) > 128
    ):
        raise KillSwitchError("KILL_SWITCH_INVALID")

    updated_at = (
        _parse_datetime(document["updated_at"])
        if document.get("updated_at") is not None
        else None
    )

    return KillSwitchStatus(
        engaged=state == ENGAGED,
        scope=str(scope),
        reason_code=reason_code,
        updated_at=updated_at,
        campaign_id=campaign_id if isinstance(campaign_id, str) else None,
    )


def evaluate_kill_switch(path: Path | None, campaign_id: str | None) -> list[str]:
    """Return refusal codes contributed by the external kill switch.

    ``path is None`` means no external source is configured; the caller keeps
    relying on the in-request ``kill_switch`` flag and the existing behaviour is
    preserved (backwards compatible).
    """

    if path is None:
        return []
    try:
        status = read_kill_switch(path)
    except KillSwitchError as exc:
        return [str(exc)]

    if not status.engaged:
        return []
    if status.scope == "campaign" and status.campaign_id != campaign_id:
        return []
    return ["KILL_SWITCH_ACTIVE"]
