#!/usr/bin/env python3
"""Read-only liveness/readiness contract for Hermes Security Labs (Lane C).

Why this exists
---------------
``platform/scripts/lab_lifecycle.py`` can dispatch a ``status`` action, but the
shipped ``status`` scripts answer a *liveness* question: "is the container or
process there?". A container that is up is **not** a lab that is READY. Lane C
separates the two concepts and makes the distinction machine-readable:

* **liveness**  - the runtime object exists and is not dead (dispatcher status);
* **readiness** - an explicit, per-environment probe/smoke contract says the lab
  answers the way a consumer needs before any authorised activity starts.

Design constraints honoured here
--------------------------------
- no change to the lab-manifest schema and no change to the target registry:
  readiness adapters live in their own directory,
  ``platform/lab-readiness/adapters/<env_id>.yaml``;
- adapters are **declarative and typed**: every check has an allowlisted ``kind``
  and validated parameters. There is no generic shell, no ``shell=True``, no
  free-form command field anywhere in this module;
- probes are non-offensive: loopback HTTP GET / loopback TCP connect / the
  already-allowlisted ``status`` lifecycle action. No smoke exploitation, no
  payloads, no writes;
- **fail-closed**: an executable lab (dispatchable manifest that declares
  ``start``) without a valid readiness adapter is reported as ``unknown`` with a
  failure reason and a non-zero exit code. Missing evidence never reads as READY;
- deterministic and injectable: :func:`evaluate` takes an executor, so contract
  tests run with a fake executor and touch no runtime at all;
- Lane A compatible: unknown/extra manifest keys are ignored and the environment
  identity is resolved through a tolerant key lookup, so a rebase on Lane A's
  environment contract does not break this module.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse, urlunparse

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency declared in docs
    raise SystemExit("PyYAML is required to use platform/scripts/lab_readiness.py") from exc

PLATFORM_DIR = Path(__file__).resolve().parents[1]
ADAPTERS_DIRNAME = Path("lab-readiness") / "adapters"

SCHEMA_VERSION = 1

#: Lifecycle states this model can report. ``live_not_ready`` is the whole point
#: of Lane C: alive is not ready.
STATE_UNKNOWN = "unknown"
STATE_DOWN = "down"
STATE_LIVE_NOT_READY = "live_not_ready"
STATE_READY = "ready"

LIFECYCLE_STATES: tuple[str, ...] = (STATE_UNKNOWN, STATE_DOWN, STATE_LIVE_NOT_READY, STATE_READY)

#: Allowlisted, non-offensive probe kinds. Anything else is rejected at load time.
LIVENESS_KINDS: frozenset[str] = frozenset({"lifecycle_status"})
READINESS_KINDS: frozenset[str] = frozenset({"http_get", "tcp_connect"})

LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

MAX_TIMEOUT_SECONDS = 30

# Stable failure reason codes (consumed by CI and by operators).
REASON_ADAPTER_MISSING = "READINESS_ADAPTER_MISSING"
REASON_ADAPTER_INVALID = "READINESS_ADAPTER_INVALID"
REASON_ENV_UNKNOWN = "ENVIRONMENT_UNKNOWN"
REASON_LIVENESS_FAILED = "LIVENESS_CHECK_FAILED"
REASON_READINESS_FAILED = "READINESS_CHECK_FAILED"
REASON_READINESS_NOT_EVALUATED = "READINESS_NOT_EVALUATED_LIVENESS_FAILED"
REASON_NO_READINESS_CHECKS = "READINESS_CONTRACT_EMPTY"
REASON_PORT_ENV_INVALID = "READINESS_PORT_ENV_INVALID"

#: Optional, per-check port override. The adapter names ONE environment variable
#: whose value may replace **only the port** of an already loopback-validated
#: check. There is no template expansion, no host/scheme/path/query/command
#: substitution: the sole mutable field is the TCP port number.
PORT_ENV_KEY = "port_env"
PORT_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

MIN_PORT = 1
MAX_PORT = 65535

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_FAIL_CLOSED = 2


class ReadinessContractError(Exception):
    """The readiness contract for an environment cannot be used as written."""


# --------------------------------------------------------------------------- #
# Adapter model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Check:
    """One declarative, typed check. No command strings, ever."""

    id: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "params": dict(self.params), "description": self.description}


@dataclass(frozen=True)
class Adapter:
    env_id: str
    source: Path
    liveness: tuple[Check, ...]
    readiness: tuple[Check, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "source": self.source.relative_to(PLATFORM_DIR).as_posix(),
            "liveness": [check.as_dict() for check in self.liveness],
            "readiness": [check.as_dict() for check in self.readiness],
        }


def adapters_dir() -> Path:
    return PLATFORM_DIR / ADAPTERS_DIRNAME


def _require_loopback(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: only http:// probes are allowed ({url})")
    host = (parsed.hostname or "").strip()
    if host not in LOOPBACK_HOSTS:
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: probe host must be loopback, got '{host}' ({url})"
        )
    if parsed.query or parsed.params:
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: probe URL must not carry a query ({url})")


def _timeout(raw: Any, default: int = 5) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: timeout_seconds must be an integer")
    if raw <= 0 or raw > MAX_TIMEOUT_SECONDS:
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: timeout_seconds must be in 1..{MAX_TIMEOUT_SECONDS}"
        )
    return raw


def _port_env_name(raw: Any, check_id: str) -> str | None:
    """Validate the OPTIONAL environment-variable name declared by a check.

    The adapter may name exactly one variable; the name itself is strictly
    validated so an adapter can never smuggle an expression or a shell fragment
    through this field.
    """
    if raw is None:
        return None
    if not isinstance(raw, str) or not PORT_ENV_NAME_RE.match(raw):
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: check '{check_id}' {PORT_ENV_KEY} must match "
            f"{PORT_ENV_NAME_RE.pattern}"
        )
    return raw


def resolve_port(check: Check, environ: Mapping[str, str] | None = None) -> int:
    """Return the effective port for a check.

    * no ``port_env`` declared, or the variable is absent  -> the committed
      default port from the validated adapter (exact legacy behaviour);
    * variable present and a valid integer in 1..65535     -> that port;
    * variable present and anything else                   -> fail closed.

    There is never a silent fallback to the default for a *present but invalid*
    value.
    """
    default_port = check.params["port"]
    env_name = check.params.get(PORT_ENV_KEY)
    if not env_name:
        return int(default_port)
    source = os.environ if environ is None else environ
    if env_name not in source:
        return int(default_port)
    raw = source[env_name]
    if not isinstance(raw, str):
        raise ReadinessContractError(
            f"{REASON_PORT_ENV_INVALID}: {env_name} must be an integer port in "
            f"{MIN_PORT}..{MAX_PORT}"
        )
    candidate = raw.strip()
    if not (candidate.isascii() and candidate.isdigit()):
        raise ReadinessContractError(
            f"{REASON_PORT_ENV_INVALID}: {env_name}={raw!r} is not an integer port"
        )
    value = int(candidate)
    if not (MIN_PORT <= value <= MAX_PORT):
        raise ReadinessContractError(
            f"{REASON_PORT_ENV_INVALID}: {env_name}={raw!r} is outside {MIN_PORT}..{MAX_PORT}"
        )
    return value


def effective_url(check: Check, environ: Mapping[str, str] | None = None) -> str:
    """Rebuild an ``http_get`` URL with only the port replaced.

    Scheme, host, path, params, query and fragment are taken verbatim from the
    already loopback-validated adapter URL.
    """
    parsed = urlparse(check.params["url"])
    port = resolve_port(check, environ)
    host = parsed.hostname or ""
    netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _parse_check(raw: Any, allowed: frozenset[str], section: str) -> Check:
    if not isinstance(raw, dict):
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: {section} entry is not a mapping")
    check_id = str(raw.get("id", "")).strip()
    kind = str(raw.get("kind", "")).strip()
    if not check_id:
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: {section} entry is missing 'id'")
    if kind not in allowed:
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: {section} check '{check_id}' has kind '{kind}' "
            f"(allowed: {', '.join(sorted(allowed))})"
        )

    params: dict[str, Any] = {}
    if kind == "lifecycle_status":
        params["timeout_seconds"] = _timeout(raw.get("timeout_seconds"), default=20)
    elif kind == "http_get":
        url = str(raw.get("url", "")).strip()
        if not url:
            raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: http_get check '{check_id}' needs 'url'")
        _require_loopback(url)
        expect_status = raw.get("expect_status", 200)
        if isinstance(expect_status, bool) or not isinstance(expect_status, int):
            raise ReadinessContractError(
                f"{REASON_ADAPTER_INVALID}: http_get check '{check_id}' expect_status must be an integer"
            )
        params["url"] = url
        params["expect_status"] = expect_status
        params["timeout_seconds"] = _timeout(raw.get("timeout_seconds"))
        parsed_url = urlparse(url)
        try:
            explicit_port = parsed_url.port
        except ValueError as exc:
            raise ReadinessContractError(
                f"{REASON_ADAPTER_INVALID}: http_get check '{check_id}' has a non-integer port ({url})"
            ) from exc
        default_http_port = explicit_port if explicit_port is not None else 80
        if not (MIN_PORT <= default_http_port <= MAX_PORT):
            raise ReadinessContractError(
                f"{REASON_ADAPTER_INVALID}: http_get check '{check_id}' has an invalid port"
            )
        params["port"] = default_http_port
        port_env = _port_env_name(raw.get(PORT_ENV_KEY), check_id)
        if port_env is not None:
            params[PORT_ENV_KEY] = port_env
        body_contains = raw.get("expect_body_contains")
        if body_contains is not None:
            if not isinstance(body_contains, str) or not body_contains:
                raise ReadinessContractError(
                    f"{REASON_ADAPTER_INVALID}: http_get check '{check_id}' "
                    "expect_body_contains must be a non-empty string"
                )
            params["expect_body_contains"] = body_contains
    elif kind == "tcp_connect":
        host = str(raw.get("host", "127.0.0.1")).strip()
        if host not in LOOPBACK_HOSTS:
            raise ReadinessContractError(
                f"{REASON_ADAPTER_INVALID}: tcp_connect check '{check_id}' host must be loopback"
            )
        port = raw.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
            raise ReadinessContractError(
                f"{REASON_ADAPTER_INVALID}: tcp_connect check '{check_id}' needs a valid 'port'"
            )
        params["host"] = host
        params["port"] = port
        params["timeout_seconds"] = _timeout(raw.get("timeout_seconds"))
        port_env = _port_env_name(raw.get(PORT_ENV_KEY), check_id)
        if port_env is not None:
            params[PORT_ENV_KEY] = port_env

    return Check(id=check_id, kind=kind, params=params, description=str(raw.get("description", "")))


def parse_adapter(env_id: str, data: Any, source: Path) -> Adapter:
    """Validate one adapter document. Unknown top-level keys are ignored on purpose
    so a Lane A rebase that adds contract fields cannot break Lane C."""
    if not isinstance(data, dict):
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: adapter is not a mapping ({source})")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION})"
        )

    declared_env = str(data.get("env_id", "")).strip()
    if declared_env and declared_env != env_id:
        raise ReadinessContractError(
            f"{REASON_ADAPTER_INVALID}: adapter env_id '{declared_env}' does not match file name '{env_id}'"
        )

    raw_liveness = data.get("liveness", [])
    raw_readiness = data.get("readiness", [])
    if not isinstance(raw_liveness, list) or not isinstance(raw_readiness, list):
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: liveness/readiness must be lists")

    liveness = tuple(_parse_check(item, LIVENESS_KINDS, "liveness") for item in raw_liveness)
    readiness = tuple(_parse_check(item, READINESS_KINDS, "readiness") for item in raw_readiness)

    if not readiness:
        raise ReadinessContractError(f"{REASON_NO_READINESS_CHECKS}: adapter declares no readiness checks")

    ids = [c.id for c in liveness] + [c.id for c in readiness]
    if len(ids) != len(set(ids)):
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: duplicate check ids in {source.name}")

    if not liveness:
        # Liveness is always meaningful for a dispatchable lab; default to the
        # allowlisted status action rather than silently skipping it.
        liveness = (Check(id="lifecycle-status", kind="lifecycle_status", params={"timeout_seconds": 20}),)

    return Adapter(env_id=env_id, source=source, liveness=liveness, readiness=readiness)


def load_adapter(env_id: str, root: Path | None = None) -> Adapter:
    directory = root if root is not None else adapters_dir()
    path = directory / f"{env_id}.yaml"
    if not path.is_file():
        raise ReadinessContractError(
            f"{REASON_ADAPTER_MISSING}: no readiness adapter at "
            f"{path.name} in {directory.as_posix()}"
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ReadinessContractError(f"{REASON_ADAPTER_INVALID}: invalid YAML in {path}: {exc}") from exc
    return parse_adapter(env_id, data, path)


def known_adapters(root: Path | None = None) -> tuple[str, ...]:
    directory = root if root is not None else adapters_dir()
    if not directory.is_dir():
        return ()
    return tuple(sorted(path.stem for path in directory.glob("*.yaml")))


# --------------------------------------------------------------------------- #
# Executors
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CheckResult:
    id: str
    kind: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "passed": self.passed, "detail": self.detail}


class Executor(Protocol):
    def run(self, env_id: str, check: Check) -> CheckResult:  # pragma: no cover - protocol
        ...


class DefaultExecutor:
    """Executes the allowlisted probe kinds. Read-only and non-offensive."""

    def __init__(self, *, dispatcher: Path | None = None, python: str | None = None) -> None:
        self.dispatcher = dispatcher or (PLATFORM_DIR / "scripts" / "lab_lifecycle.py")
        self.python = python or sys.executable or "python3"

    def run(self, env_id: str, check: Check) -> CheckResult:
        if check.kind == "lifecycle_status":
            return self._lifecycle_status(env_id, check)
        if check.kind == "http_get":
            return self._http_get(check)
        if check.kind == "tcp_connect":
            return self._tcp_connect(check)
        # Unreachable for parsed adapters; fail closed anyway.
        return CheckResult(check.id, check.kind, False, f"unsupported check kind '{check.kind}'")

    def _lifecycle_status(self, env_id: str, check: Check) -> CheckResult:
        argv = [self.python, str(self.dispatcher), "run", env_id, "status"]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, allowlisted action
                argv,
                capture_output=True,
                text=True,
                timeout=check.params["timeout_seconds"],
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(check.id, check.kind, False, "status action timed out")
        except OSError as exc:
            return CheckResult(check.id, check.kind, False, f"status action could not run: {exc}")
        if completed.returncode != 0:
            return CheckResult(check.id, check.kind, False, f"status exit={completed.returncode}")
        return CheckResult(check.id, check.kind, True, "status exit=0")

    def _http_get(self, check: Check) -> CheckResult:
        expect = check.params["expect_status"]
        try:
            url = effective_url(check)
        except ReadinessContractError as exc:
            return CheckResult(check.id, check.kind, False, str(exc))
        request = urllib.request.Request(url, method="GET")  # noqa: S310 - loopback-validated http
        try:
            with urllib.request.urlopen(request, timeout=check.params["timeout_seconds"]) as response:  # noqa: S310
                status = int(response.status)
                body = response.read(4096).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return CheckResult(check.id, check.kind, False, f"GET {url} failed: {exc}")
        if status != expect:
            return CheckResult(check.id, check.kind, False, f"GET {url} status={status} expected={expect}")
        needle = check.params.get("expect_body_contains")
        if needle and needle not in body:
            return CheckResult(check.id, check.kind, False, f"GET {url} body missing expected marker")
        return CheckResult(check.id, check.kind, True, f"GET {url} status={status}")

    def _tcp_connect(self, check: Check) -> CheckResult:
        host = check.params["host"]
        try:
            port = resolve_port(check)
        except ReadinessContractError as exc:
            return CheckResult(check.id, check.kind, False, str(exc))
        try:
            with socket.create_connection((host, port), timeout=check.params["timeout_seconds"]):
                pass
        except OSError as exc:
            return CheckResult(check.id, check.kind, False, f"tcp {host}:{port} failed: {exc}")
        return CheckResult(check.id, check.kind, True, f"tcp {host}:{port} open")


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def _now_iso(now: datetime | None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _result(
    *,
    env_id: str,
    lab_id: str,
    state: str,
    liveness: list[CheckResult],
    readiness: list[CheckResult],
    reasons: list[str],
    adapter: Adapter | None,
    now: datetime | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "lab_id": lab_id,
        "environment_id": env_id,
        "lifecycle_state": state,
        "ready": state == STATE_READY,
        "live": state in {STATE_LIVE_NOT_READY, STATE_READY},
        "liveness": {
            "state": "pass" if liveness and all(c.passed for c in liveness) else ("fail" if liveness else "unknown"),
            "checks": [c.as_dict() for c in liveness],
        },
        "readiness": {
            "state": "pass" if readiness and all(c.passed for c in readiness) else ("fail" if readiness else "unknown"),
            "checks": [c.as_dict() for c in readiness],
        },
        "failure_reasons": reasons,
        "adapter": adapter.as_dict() if adapter is not None else None,
        "observed_at": _now_iso(now),
    }


def _lab_id(env_id: str, manifest: dict[str, Any] | None) -> str:
    """Lane A tolerant identity lookup: any of these keys may carry the lab id."""
    if not manifest:
        return env_id
    for key in ("lab_id", "lab", "id", "environment_id", "env_id"):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return env_id


def evaluate(
    env_id: str,
    *,
    executor: Executor | None = None,
    adapter_root: Path | None = None,
    manifest: dict[str, Any] | None = None,
    executable: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Produce the read-only status/readiness result document.

    ``executable`` marks a lab that can actually be started. For such a lab a
    missing or invalid adapter is fail-closed (``unknown`` + non-zero exit).
    """
    lab_id = _lab_id(env_id, manifest)
    try:
        adapter = load_adapter(env_id, adapter_root)
    except ReadinessContractError as exc:
        reason = str(exc).split(":", 1)[0]
        if not executable and reason == REASON_ADAPTER_MISSING:
            return _result(
                env_id=env_id,
                lab_id=lab_id,
                state=STATE_UNKNOWN,
                liveness=[],
                readiness=[],
                reasons=[f"{REASON_ADAPTER_MISSING}: environment is not executable; readiness not required"],
                adapter=None,
                now=now,
            )
        return _result(
            env_id=env_id,
            lab_id=lab_id,
            state=STATE_UNKNOWN,
            liveness=[],
            readiness=[],
            reasons=[str(exc)],
            adapter=None,
            now=now,
        )

    runner = executor or DefaultExecutor()

    liveness = [runner.run(env_id, check) for check in adapter.liveness]
    reasons: list[str] = []
    if not all(c.passed for c in liveness):
        for check in liveness:
            if not check.passed:
                reasons.append(f"{REASON_LIVENESS_FAILED}: {check.id}: {check.detail}")
        reasons.append(REASON_READINESS_NOT_EVALUATED)
        return _result(
            env_id=env_id,
            lab_id=lab_id,
            state=STATE_DOWN,
            liveness=liveness,
            readiness=[],
            reasons=reasons,
            adapter=adapter,
            now=now,
        )

    readiness = [runner.run(env_id, check) for check in adapter.readiness]
    if not all(c.passed for c in readiness):
        for check in readiness:
            if not check.passed:
                reasons.append(f"{REASON_READINESS_FAILED}: {check.id}: {check.detail}")
        # Alive but not ready: the state Lane C exists to express.
        return _result(
            env_id=env_id,
            lab_id=lab_id,
            state=STATE_LIVE_NOT_READY,
            liveness=liveness,
            readiness=readiness,
            reasons=reasons,
            adapter=adapter,
            now=now,
        )

    return _result(
        env_id=env_id,
        lab_id=lab_id,
        state=STATE_READY,
        liveness=liveness,
        readiness=readiness,
        reasons=[],
        adapter=adapter,
        now=now,
    )


def exit_code_for(result: dict[str, Any]) -> int:
    state = result.get("lifecycle_state")
    if state == STATE_READY:
        return EXIT_READY
    if state == STATE_UNKNOWN:
        return EXIT_FAIL_CLOSED
    return EXIT_NOT_READY


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _dispatchable() -> dict[str, dict[str, Any]]:
    """Reuse the dispatcher's manifest discovery without importing runtime state."""
    import importlib.util

    dispatcher_path = PLATFORM_DIR / "scripts" / "lab_lifecycle.py"
    spec = importlib.util.spec_from_file_location("_lane_c_lab_lifecycle", dispatcher_path)
    if not spec or not spec.loader:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return {env_id: data for env_id, (_path, data) in module.dispatchable_manifests().items()}


def is_executable_manifest(manifest: dict[str, Any]) -> bool:
    lifecycle = manifest.get("lifecycle")
    if not isinstance(lifecycle, list):
        return False
    return "start" in {str(item) for item in lifecycle}


def cmd_status(args: argparse.Namespace) -> int:
    manifests = _dispatchable()
    manifest = manifests.get(args.env_id)
    if manifest is None:
        result = _result(
            env_id=args.env_id,
            lab_id=args.env_id,
            state=STATE_UNKNOWN,
            liveness=[],
            readiness=[],
            reasons=[f"{REASON_ENV_UNKNOWN}: no dispatchable manifest for '{args.env_id}'"],
            adapter=None,
            now=None,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return EXIT_FAIL_CLOSED

    if args.contract_only:
        try:
            adapter = load_adapter(args.env_id)
        except ReadinessContractError as exc:
            print(f"FAIL-CLOSED\t{args.env_id}\t{exc}", file=sys.stderr)
            return EXIT_FAIL_CLOSED
        print(json.dumps(adapter.as_dict(), indent=2, sort_keys=True))
        return EXIT_READY

    result = evaluate(
        args.env_id,
        manifest=manifest,
        executable=is_executable_manifest(manifest),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code_for(result)


def cmd_coverage(args: argparse.Namespace) -> int:
    manifests = _dispatchable()
    rows: list[dict[str, Any]] = []
    gaps = 0
    for env_id, manifest in sorted(manifests.items()):
        executable = is_executable_manifest(manifest)
        try:
            load_adapter(env_id)
        except ReadinessContractError as exc:
            state, detail = "MISSING", str(exc)
            if executable:
                gaps += 1
        else:
            state, detail = "PRESENT", ""
        rows.append(
            {"env_id": env_id, "executable": executable, "adapter": state, "detail": detail}
        )
    if args.json:
        print(json.dumps({"environments": rows, "executable_gaps": gaps}, indent=2, sort_keys=True))
    else:
        print("env_id\texecutable\tadapter")
        for row in rows:
            print(f"{row['env_id']}\t{row['executable']}\t{row['adapter']}")
        print(f"executable_gaps={gaps}")
    if args.strict and gaps:
        return EXIT_FAIL_CLOSED
    return EXIT_READY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only liveness/readiness contract for supported labs (alive != ready)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="emit the JSON status/readiness result for one environment")
    status.add_argument("env_id")
    status.add_argument(
        "--contract-only",
        action="store_true",
        help="print the validated adapter contract and run no probes",
    )
    status.set_defaults(func=cmd_status)

    coverage = subparsers.add_parser("coverage", help="report adapter coverage across dispatchable environments")
    coverage.add_argument("--json", action="store_true")
    coverage.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when an executable environment has no readiness adapter",
    )
    coverage.set_defaults(func=cmd_coverage)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
