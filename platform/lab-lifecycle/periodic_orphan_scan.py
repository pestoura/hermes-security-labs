"""Periodic, fail-closed orchestration for read-only orphan observations.

The runtime enumerator is injected by the deployment adapter. This module
schedules/normalizes observations only; it never deletes, stops or mutates
resources and never performs automatic reconciliation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping

ResourceScanner = Callable[[], Iterable[Mapping[str, Any]]]


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed


def scan_due(*, now: str, last_observed_at: str | None, interval_seconds: int) -> bool:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    current = _parse(now)
    if last_observed_at is None:
        return True
    return current >= _parse(last_observed_at) + timedelta(seconds=interval_seconds)


def build_periodic_observation(
    *,
    observation_id: str,
    observed_at: str,
    lifecycle_records: Iterable[Mapping[str, Any]],
    scanner: ResourceScanner,
) -> dict[str, Any]:
    if not observation_id:
        raise ValueError("observation_id is required")
    _parse(observed_at)

    records = [dict(item) for item in lifecycle_records]
    try:
        resources = [dict(item) for item in scanner()]
    except Exception:  # runtime integration failure is represented, never hidden
        return {
            "schema_version": "1.0.0",
            "observation_id": observation_id,
            "observed_at": observed_at,
            "scanner_state": "UNAVAILABLE",
            "lifecycle_records": records,
            "resources": [],
        }

    return {
        "schema_version": "1.0.0",
        "observation_id": observation_id,
        "observed_at": observed_at,
        "scanner_state": "COMPLETE",
        "lifecycle_records": records,
        "resources": resources,
    }
