from __future__ import annotations

import ast
import importlib.util
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from runner_protocol_v2 import validate_semantics

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"
HANDOFF_PATH = ROOT / "platform" / "gateway-protocol" / "runner_handoff.py"
AUTHORIZATION_REF = "tb1-authz:v1:" + ("1" * 64)
CAMPAIGN_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load("webgoat_l1_adapter_test", MODULE_PATH)
handoff = _load("webgoat_l1_handoff_compat_test", HANDOFF_PATH)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass
class StaticResolver:
    binding: Any | None

    def resolve(self, authorization_ref: str):
        del authorization_ref
        return self.binding


@dataclass(frozen=True)
class VerifiedHandoffStub:
    authorization_ref: str = AUTHORIZATION_REF


@dataclass(frozen=True)
class VerifiedBinding:
    authorization_ref: str
    issued_at: str
    expires_at: str
    campaign_id: str
    run_id: str
    step_id: str
    operation_id: str
    operation_version: str
    operation_parameters_sha256: str
    capability_id: str
    target_sha256: str
    intrusiveness_level: str


class FakeProbe:
    def __init__(self, *, status: int = 200, headers=()):
        self.status = status
        self.headers = tuple(headers)
        self.calls = 0
        self.timeouts: list[float] = []

    def get(self, *, timeout_seconds: float):
        self.calls += 1
        self.timeouts.append(timeout_seconds)
        return adapter.ProbeResponse(status=self.status, headers=self.headers)


def _canonical_input(
    capability: str = "web.discovery.headers",
    *,
    parameters: dict[str, Any] | None = None,
    target: dict[str, str] | None = None,
    operation_id: str | None = None,
    operation_version: str = "1.0.0",
    intrusiveness_level: str = "L1",
) -> dict[str, Any]:
    return {
        "operation_id": operation_id or capability,
        "operation_version": operation_version,
        "intrusiveness_level": intrusiveness_level,
        "target": target or {"type": "lab-asset", "value": "webgoat-web"},
        "parameters": {} if parameters is None else parameters,
    }


def _request(
    capability: str = "web.discovery.headers",
    *,
    input_payload: dict[str, Any] | None = None,
    replay_key: str = "fixture-webgoat-key-one",
    authorization_ref: str = AUTHORIZATION_REF,
) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
        },
        "emitted_at": "2026-08-09T18:30:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": replay_key,
        "operation": {
            "capability_id": capability,
            "input": _canonical_input(capability)
            if input_payload is None
            else input_payload,
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
        },
        "retry_policy": {
            "max_attempts": 1,
            "retryable_error_codes": [],
        },
        "cancellation_policy": {
            "mode": "cooperative",
            "grace_period_ms": 0,
        },
    }


def _verified_for(request: dict[str, Any], **overrides: Any) -> VerifiedBinding:
    payload = request["operation"]["input"]
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "authorization_ref": request["authorization_ref"],
        "issued_at": _iso(now - timedelta(seconds=30)),
        "expires_at": _iso(now + timedelta(minutes=5)),
        "campaign_id": request["correlation"]["campaign_id"],
        "run_id": request["correlation"]["run_id"],
        "step_id": request["correlation"]["step_id"],
        "operation_id": payload["operation_id"],
        "operation_version": payload["operation_version"],
        "operation_parameters_sha256": adapter.authorization_contract.canonical_parameters_sha256(
            payload["parameters"]
        ),
        "capability_id": request["operation"]["capability_id"],
        "target_sha256": adapter.gateway_contract.canonical_target_digest(payload["target"]),
        "intrusiveness_level": payload["intrusiveness_level"],
    }
    values.update(overrides)
    return VerifiedBinding(**values)


def _build(
    tmp_path: Path,
    request: dict[str, Any],
    probe: FakeProbe,
    *,
    binding: Any | None = None,
):
    return adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=StaticResolver(
            _verified_for(request) if binding is None else binding
        ),
        probe=probe,
    )


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    message = result["messages"][0]
    validate_semantics(message)
    return message


def _handoff_message(
    capability: str = "web.discovery.headers",
    *,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "operation": {
            "id": capability,
            "version": "1.0.0",
            "parameters": {} if parameters is None else parameters,
        },
        "target": {"type": "lab-asset", "value": "webgoat-web"},
    }
    roe_step_request = {
        "capability": capability,
        "intrusiveness_level": "L1",
    }
    message = handoff._assemble_message(
        request,
        roe_step_request,
        object(),
        VerifiedHandoffStub(),
        handoff.RunnerHandoffConfig(),
    )
    validate_semantics(message)
    return message


def test_default_authorization_resolver_denies_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        probe=probe,
    )
    outcome = _outcome(runner.dispatch(_request()))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


def test_incomplete_resolved_metadata_denies_before_network(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe()
    runner = _build(tmp_path, request, probe, binding=VerifiedHandoffStub())
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


@pytest.mark.parametrize(
    "field, value",
    [
        ("authorization_ref", "tb1-authz:v1:" + ("2" * 64)),
        ("campaign_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        ("run_id", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        ("step_id", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        ("operation_id", "web.discovery.tls"),
        ("operation_version", "9.9.9"),
        ("capability_id", "web.discovery.tls"),
        ("intrusiveness_level", "L2"),
        ("operation_parameters_sha256", "d" * 64),
        ("target_sha256", "e" * 64),
    ],
)
def test_verified_authorization_binding_mismatch_denies_before_network(
    tmp_path: Path, field: str, value: str
) -> None:
    request = _request(
        input_payload=_canonical_input(parameters={"follow_redirects": False})
    )
    probe = FakeProbe()
    binding = replace(_verified_for(request), **{field: value})
    runner = _build(tmp_path, request, probe, binding=binding)
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


def test_expired_verified_authorization_denies_before_network(tmp_path: Path) -> None:
    request = _request()
    now = datetime.now(timezone.utc)
    binding = replace(
        _verified_for(request),
        issued_at=_iso(now - timedelta(minutes=2)),
        expires_at=_iso(now - timedelta(seconds=1)),
    )
    probe = FakeProbe()
    runner = _build(tmp_path, request, probe, binding=binding)
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert probe.calls == 0


def test_future_verified_authorization_denies_before_network(tmp_path: Path) -> None:
    request = _request()
    now = datetime.now(timezone.utc)
    binding = replace(
        _verified_for(request),
        issued_at=_iso(now + timedelta(minutes=1)),
        expires_at=_iso(now + timedelta(minutes=5)),
    )
    probe = FakeProbe()
    runner = _build(tmp_path, request, probe, binding=binding)
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert probe.calls == 0


def test_headers_effect_accepts_exact_verified_binding_and_sanitizes(tmp_path: Path) -> None:
    request = _request(
        input_payload=_canonical_input(parameters={"follow_redirects": False})
    )
    probe = FakeProbe(
        status=200,
        headers=(
            ("Server", "WebGoat"),
            ("Set-Cookie", "session=secret"),
            ("X-Test", "safe-value"),
        ),
    )
    runner = _build(tmp_path, request, probe)
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "PASS"
    output = outcome["output"]
    assert output["target_id"] == "webgoat-web"
    assert output["environment_id"] == "webgoat"
    assert output["capability_id"] == "web.discovery.headers"
    assert output["redirects_followed"] is False
    assert output["http_status"] == 200
    assert {"name": "server", "value": "WebGoat"} in output["headers"]
    assert {"name": "x-test", "value": "safe-value"} in output["headers"]
    assert all(item["name"] != "set-cookie" for item in output["headers"])
    assert probe.calls == 1
    assert probe.timeouts == [5.0]


def test_tls_effect_accepts_exact_verified_binding(tmp_path: Path) -> None:
    request = _request(
        "web.discovery.tls",
        replay_key="fixture-webgoat-key-two",
    )
    probe = FakeProbe(status=200)
    runner = _build(tmp_path, request, probe)
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "PASS"
    assert outcome["output"]["assessment"] == "PLAINTEXT_HTTP"
    assert outcome["output"]["tls_enabled"] is False
    assert probe.calls == 1


def test_real_handoff_message_binds_to_verified_metadata(tmp_path: Path) -> None:
    message = _handoff_message(
        "web.discovery.headers",
        parameters={"follow_redirects": False},
    )
    probe = FakeProbe(status=200, headers=(("Server", "WebGoat"),))
    runner = _build(tmp_path, message, probe)
    outcome = _outcome(runner.dispatch(message))
    assert outcome["status"] == "PASS"
    assert probe.calls == 1
    assert message["operation"]["input"]["target"] == {
        "type": "lab-asset",
        "value": "webgoat-web",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"follow_redirects": False},
        _canonical_input(parameters={"follow_redirects": True}),
        _canonical_input(parameters={"url": "https://example.com"}),
        _canonical_input(target={"type": "lab-asset", "value": "dvwa-web"}),
        _canonical_input(target={"type": "hostname", "value": "webgoat"}),
        _canonical_input(operation_id="web.discovery.tls"),
        _canonical_input(operation_version="2.0.0"),
        _canonical_input(intrusiveness_level="L2"),
    ],
)
def test_noncanonical_or_mismatched_input_is_refused_before_network(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    request = _request(input_payload=payload)
    probe = FakeProbe()
    runner = adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=StaticResolver(None),
        probe=probe,
    )
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "INVALID_REQUEST"
    assert probe.calls == 0


def test_unknown_handoff_envelope_field_is_refused_before_network(tmp_path: Path) -> None:
    payload = _canonical_input()
    payload["bypass"] = True
    request = _request(input_payload=payload)
    probe = FakeProbe()
    runner = adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=StaticResolver(None),
        probe=probe,
    )
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert probe.calls == 0


def test_exact_replay_returns_durable_outcome_without_second_effect(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe(status=204, headers=(("X-Replay", "one"),))
    runner = _build(tmp_path, request, probe)
    first = _outcome(runner.dispatch(request))
    second = _outcome(runner.dispatch(request))
    assert first == second
    assert first["status"] == "PASS"
    assert probe.calls == 1


def test_same_idempotency_key_with_changed_effect_refuses_before_second_effect(
    tmp_path: Path,
) -> None:
    request = _request()
    probe = FakeProbe()
    runner = _build(tmp_path, request, probe)
    first = _outcome(runner.dispatch(request))
    assert first["status"] == "PASS"

    changed = _request()
    changed["timeout_budget"]["hard_timeout_ms"] = 6000
    runner.authorization_resolver = StaticResolver(_verified_for(changed))
    conflict = _outcome(runner.dispatch(changed))
    assert conflict["status"] == "REFUSED"
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert probe.calls == 1


def test_unsupported_capability_is_refused_before_network(tmp_path: Path) -> None:
    request = _request(
        "web.validation.sql-injection",
        input_payload=_canonical_input(
            "web.validation.sql-injection",
            intrusiveness_level="L2",
        ),
        replay_key="fixture-webgoat-key-three",
    )
    probe = FakeProbe()
    runner = adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=StaticResolver(None),
        probe=probe,
    )
    outcome = _outcome(runner.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert probe.calls == 0


def test_source_contains_no_generic_execution_surface() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    dangerous_calls: list[str] = []
    shell_true = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                dangerous_calls.append(node.func.id)
            elif (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "system"
            ):
                dangerous_calls.append("os.system")
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    shell_true = True

    assert not any(
        name == "subprocess" or name.startswith("subprocess.")
        for name in imported_modules
    )
    assert dangerous_calls == []
    assert shell_true is False
    assert 'TARGET_HOST = "webgoat"' in source
    assert 'TARGET_ENVELOPE = {"type": "lab-asset", "value": TARGET_ID}' in source
