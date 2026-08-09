from __future__ import annotations

import ast
import importlib.util
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runner_protocol_v2 import validate_semantics

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"


def _load():
    spec = importlib.util.spec_from_file_location("webgoat_l1_adapter_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load()


@dataclass
class StaticResolver:
    binding: Any | None

    def resolve(self, authorization_ref: str):
        del authorization_ref
        return self.binding


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


def _binding(capability: str, *, target_id: str = "webgoat-web"):
    return adapter.AuthorizationBinding(
        authorization_ref="authz/tb1/webgoat-l1-0001",
        target_id=target_id,
        capability_id=capability,
        authorization_class="LAB_ONLY",
    )


def _request(
    capability: str = "web.discovery.headers",
    *,
    input_payload: dict[str, Any] | None = None,
    replay_key: str = "fixture-webgoat-key-one",
) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": str(uuid.UUID("11111111-1111-4111-8111-111111111111")),
            "run_id": str(uuid.UUID("22222222-2222-4222-8222-222222222222")),
            "step_id": str(uuid.UUID("33333333-3333-4333-8333-333333333333")),
            "attempt_id": str(uuid.UUID("44444444-4444-4444-8444-444444444444")),
        },
        "emitted_at": "2026-08-09T18:30:00Z",
        "authorization_ref": "authz/tb1/webgoat-l1-0001",
        "idempotency_key": replay_key,
        "operation": {
            "capability_id": capability,
            "input": {} if input_payload is None else input_payload,
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


def _build(tmp_path: Path, capability: str, probe: FakeProbe, *, resolver=None):
    return adapter.build_adapter(
        ledger_path=tmp_path / "ledger.sqlite3",
        authorization_resolver=resolver or StaticResolver(_binding(capability)),
        probe=probe,
    )


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    message = result["messages"][0]
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


def test_target_binding_mismatch_denies_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(
        tmp_path,
        "web.discovery.headers",
        probe,
        resolver=StaticResolver(
            _binding("web.discovery.headers", target_id="dvwa-web")
        ),
    )
    outcome = _outcome(runner.dispatch(_request()))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


def test_capability_binding_mismatch_denies_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(
        tmp_path,
        "web.discovery.headers",
        probe,
        resolver=StaticResolver(_binding("web.discovery.tls")),
    )
    outcome = _outcome(runner.dispatch(_request()))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


def test_headers_effect_is_target_bound_and_sanitized(tmp_path: Path) -> None:
    probe = FakeProbe(
        status=200,
        headers=(
            ("Server", "WebGoat"),
            ("Set-Cookie", "session=secret"),
            ("X-Test", "safe-value"),
        ),
    )
    runner = _build(tmp_path, "web.discovery.headers", probe)
    outcome = _outcome(runner.dispatch(_request()))
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
    assert outcome["evidence_refs"][0]["kind"] == "execution"
    assert "uri" not in outcome["evidence_refs"][0]


def test_tls_effect_reports_plaintext_transport_without_arbitrary_target(tmp_path: Path) -> None:
    probe = FakeProbe(status=200)
    runner = _build(tmp_path, "web.discovery.tls", probe)
    outcome = _outcome(
        runner.dispatch(
            _request(
                "web.discovery.tls",
                replay_key="fixture-webgoat-key-two",
            )
        )
    )
    assert outcome["status"] == "PASS"
    assert outcome["output"] == {
        "adapter_id": "webgoat-l1",
        "target_id": "webgoat-web",
        "environment_id": "webgoat",
        "capability_id": "web.discovery.tls",
        "http_status": 200,
        "scheme": "http",
        "tls_enabled": False,
        "plaintext_transport": True,
        "assessment": "PLAINTEXT_HTTP",
    }
    assert probe.calls == 1


def test_redirect_following_is_refused_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(tmp_path, "web.discovery.headers", probe)
    outcome = _outcome(
        runner.dispatch(
            _request(input_payload={"follow_redirects": True})
        )
    )
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "INVALID_REQUEST"
    assert probe.calls == 0


def test_arbitrary_target_fields_are_refused_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(tmp_path, "web.discovery.headers", probe)
    outcome = _outcome(
        runner.dispatch(
            _request(input_payload={"url": "https://example.com"})
        )
    )
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "INVALID_REQUEST"
    assert probe.calls == 0


def test_exact_replay_returns_durable_outcome_without_second_effect(tmp_path: Path) -> None:
    probe = FakeProbe(status=204, headers=(("X-Replay", "one"),))
    runner = _build(tmp_path, "web.discovery.headers", probe)
    request = _request()
    first = _outcome(runner.dispatch(request))
    second = _outcome(runner.dispatch(request))
    assert first == second
    assert first["status"] == "PASS"
    assert probe.calls == 1


def test_same_idempotency_key_with_changed_effect_refuses_conflict(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(tmp_path, "web.discovery.headers", probe)
    request = _request()
    first = _outcome(runner.dispatch(request))
    assert first["status"] == "PASS"
    changed = _request()
    changed["timeout_budget"]["hard_timeout_ms"] = 6000
    conflict = _outcome(runner.dispatch(changed))
    assert conflict["status"] == "REFUSED"
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert probe.calls == 1


def test_unsupported_capability_is_refused_before_network(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = _build(tmp_path, "web.discovery.headers", probe)
    outcome = _outcome(
        runner.dispatch(
            _request(
                "web.validation.sql-injection",
                replay_key="fixture-webgoat-key-three",
            )
        )
    )
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
            elif isinstance(node.func, ast.Name) and node.func.id == "execute_command":
                dangerous_calls.append("execute_command")
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    shell_true = True

    assert not any(name == "subprocess" or name.startswith("subprocess.") for name in imported_modules)
    assert dangerous_calls == []
    assert shell_true is False
    assert 'TARGET_HOST = "webgoat"' in source
    assert 'TARGET_PATH = "/WebGoat/"' in source
