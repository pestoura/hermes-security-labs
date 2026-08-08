from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


def _load_assurance():
    name = "_hex0r_assurance_readiness_probe"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / "assurance.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot load assurance contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


assurance = _load_assurance()


class ReadinessProbeError(ValueError):
    pass


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReadinessProbeError("READINESS_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReadinessProbeError("READINESS_TIMESTAMP_INVALID") from exc
    return parsed.astimezone(timezone.utc)


def probe_http_readiness(*, url: str, now: datetime | None = None, timeout_seconds: float = 2.0):
    if not url.startswith("http://127.0.0.1:") and not url.startswith("http://localhost:"):
        raise ReadinessProbeError("CONTROLLED_LOCAL_READINESS_URL_REQUIRED")
    if timeout_seconds <= 0 or timeout_seconds > 5:
        raise ReadinessProbeError("READINESS_TIMEOUT_INVALID")
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise ReadinessProbeError("READINESS_HTTP_NOT_OK")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReadinessProbeError("READINESS_PROBE_FAILED") from exc

    if not isinstance(payload, dict):
        raise ReadinessProbeError("READINESS_PAYLOAD_INVALID")
    state = payload.get("state")
    observed_at = payload.get("observed_at")
    ttl_seconds = payload.get("ttl_seconds")
    if state not in {"ready", "not_ready"}:
        raise ReadinessProbeError("READINESS_STATE_INVALID")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0 or ttl_seconds > 300:
        raise ReadinessProbeError("READINESS_TTL_INVALID")

    observed = _parse_utc(str(observed_at))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = int((current - observed).total_seconds())
    readiness = assurance.Readiness(
        state=state,
        observed_at=str(observed_at),
        ttl_seconds=ttl_seconds,
        age_seconds=age,
    )
    assurance.assert_executable_step_ready(readiness)
    return readiness


def execute_after_readiness(*, readiness: Any, effect: Callable[[], Any]) -> Any:
    assurance.assert_executable_step_ready(readiness)
    if not callable(effect):
        raise ReadinessProbeError("EXECUTABLE_EFFECT_REQUIRED")
    return effect()
