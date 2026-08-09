"""Negative controls for the fail-closed offensive execution authorization.

Contract under test (Lane G):

* ``target_id`` is the only execution authority; raw URLs/IPs deny.
* Offensive dispatch requires ``authorization_state`` in
  {LAB_ONLY, AUTHORIZED_TEST_TARGET}, execution-ready lifecycle, compatible
  health and an in-scope operation.
* UNVERIFIED / BLOCKED / EXTERNAL / missing / ambiguous / retired /
  out-of-scope deny deterministically **before** any handler is invoked.
* Safety (cleanup/stop/reset/destroy) operations stay available even for a
  denied target: a BLOCKED target must remain destroyable.
* Generic execution stays forbidden.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS_DIR = ROOT / "platform" / "targets"
MODULE_PATH = TARGETS_DIR / "execution_authorization.py"

spec = importlib.util.spec_from_file_location("hermes_execution_authorization", MODULE_PATH)
assert spec and spec.loader
execution_authorization = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = execution_authorization
spec.loader.exec_module(execution_authorization)

authorize_operation = execution_authorization.authorize_operation
guarded_dispatch = execution_authorization.guarded_dispatch
AuthorizationError = execution_authorization.AuthorizationError
AuthorizationDecision = execution_authorization.AuthorizationDecision
REASON_CODES = execution_authorization.REASON_CODES

OFFENSIVE_OPERATION = "web_vulnerability_scan"
SAFETY_OPERATION = "lab.lifecycle.destroy"


class HandlerSpy:
    """Records whether the offensive handler was ever invoked."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003 - test double
        self.calls += 1
        return {"invoked": True}


def _document(**overrides) -> dict:
    target = {
        "target_id": "lab-target",
        "environment_id": "lab-env",
        "kind": "application",
        "identity": {
            "hostname": "lab-target",
            "port": 8080,
            "protocol": "tcp",
            "scheme": "http",
            "path": "/",
            "network": "lab",
            "reachability": "lab-internal",
        },
        "authorization_state": "LAB_ONLY",
        "lifecycle": "PROVISIONED",
        "health": "UNKNOWN",
        "scope": {"allowed_operations": ["discovery", OFFENSIVE_OPERATION]},
    }
    target.update(overrides)
    return {
        "schema_version": "1.0",
        "contract": {
            "canonical_authority": "target_id",
            "fail_closed": True,
            "offensive_execution_states": ["LAB_ONLY", "AUTHORIZED_TEST_TARGET"],
        },
        "targets": [target],
    }


# --------------------------------------------------------------------------
# positive controls
# --------------------------------------------------------------------------


def test_authorized_lab_target_in_scope_is_allowed() -> None:
    decision = authorize_operation("lab-target", OFFENSIVE_OPERATION, document=_document())
    assert decision.allowed is True
    assert decision.reason_code == "ALLOW_OFFENSIVE_OPERATION"
    assert decision.operation_class == "OFFENSIVE"
    assert decision.target_id == "lab-target"


def test_authorized_test_target_state_is_allowed() -> None:
    document = _document(authorization_state="AUTHORIZED_TEST_TARGET")
    decision = authorize_operation("lab-target", OFFENSIVE_OPERATION, document=document)
    assert decision.allowed is True


def test_active_lifecycle_and_healthy_health_are_allowed() -> None:
    document = _document(lifecycle="ACTIVE", health="HEALTHY")
    assert authorize_operation("lab-target", OFFENSIVE_OPERATION, document=document).allowed


def test_guarded_dispatch_invokes_handler_once_when_allowed() -> None:
    handler = HandlerSpy()
    decision, result = guarded_dispatch(
        "lab-target",
        OFFENSIVE_OPERATION,
        handler,
        document=_document(),
    )
    assert decision.allowed is True
    assert result == {"invoked": True}
    assert handler.calls == 1


# --------------------------------------------------------------------------
# negative controls: handler is NEVER called on a denied target
# --------------------------------------------------------------------------


DENIAL_CASES = [
    ("unverified", {"authorization_state": "UNVERIFIED"}, "lab-target", "AUTHORIZATION_STATE_DENIED"),
    ("blocked", {"authorization_state": "BLOCKED"}, "lab-target", "AUTHORIZATION_STATE_DENIED"),
    ("external", {"authorization_state": "EXTERNAL"}, "lab-target", "AUTHORIZATION_STATE_DENIED"),
    ("missing_state", {"authorization_state": None}, "lab-target", "AUTHORIZATION_STATE_INVALID"),
    ("ambiguous_state", {"authorization_state": "MAYBE"}, "lab-target", "AUTHORIZATION_STATE_INVALID"),
    ("retired", {"lifecycle": "RETIRED"}, "lab-target", "TARGET_LIFECYCLE_RETIRED"),
    ("planned", {"lifecycle": "PLANNED"}, "lab-target", "TARGET_LIFECYCLE_NOT_READY"),
    ("suspended", {"lifecycle": "SUSPENDED"}, "lab-target", "TARGET_LIFECYCLE_NOT_READY"),
    ("unhealthy", {"health": "UNHEALTHY"}, "lab-target", "TARGET_HEALTH_INCOMPATIBLE"),
    ("degraded", {"health": "DEGRADED"}, "lab-target", "TARGET_HEALTH_INCOMPATIBLE"),
    ("empty_scope", {"scope": {"allowed_operations": []}}, "lab-target", "TARGET_SCOPE_EMPTY"),
    (
        "out_of_scope",
        {"scope": {"allowed_operations": ["discovery"]}},
        "lab-target",
        "OPERATION_OUT_OF_SCOPE",
    ),
    (
        "explicitly_denied",
        {
            "scope": {
                "allowed_operations": ["discovery", OFFENSIVE_OPERATION],
                "denied_operations": [OFFENSIVE_OPERATION],
            }
        },
        "lab-target",
        "OPERATION_EXPLICITLY_DENIED",
    ),
    ("unknown_target", {}, "not-registered", "TARGET_UNKNOWN"),
    ("url_authority", {}, "http://lab-target:8080/", "TARGET_ID_NOT_CANONICAL"),
    ("ip_authority", {}, "10.0.0.5:8080", "TARGET_ID_NOT_CANONICAL"),
    ("bare_ip_authority", {}, "10.0.0.5", "TARGET_ID_NOT_CANONICAL"),
    ("bare_ipv6_authority", {}, "fd00::1", "TARGET_ID_NOT_CANONICAL"),
    ("empty_target", {}, "", "TARGET_ID_MISSING"),
    ("none_target", {}, None, "TARGET_ID_MISSING"),
    ("padded_target", {}, " lab-target ", "TARGET_ID_NOT_CANONICAL"),
]


@pytest.mark.parametrize(
    ("label", "overrides", "target_id", "reason_code"),
    DENIAL_CASES,
    ids=[case[0] for case in DENIAL_CASES],
)
def test_denied_targets_never_reach_the_handler(
    label: str,
    overrides: dict,
    target_id,
    reason_code: str,
) -> None:
    document = _document(**overrides)
    decision = authorize_operation(target_id, OFFENSIVE_OPERATION, document=document)
    assert decision.allowed is False, label
    assert decision.reason_code == reason_code, label

    handler = HandlerSpy()
    with pytest.raises(AuthorizationError) as excinfo:
        guarded_dispatch(target_id, OFFENSIVE_OPERATION, handler, document=document)
    assert handler.calls == 0, label
    assert excinfo.value.decision.reason_code == reason_code


def test_missing_operation_id_denies_before_dispatch() -> None:
    handler = HandlerSpy()
    for operation_id in (None, "", "   ", 42):
        decision = authorize_operation("lab-target", operation_id, document=_document())
        assert decision.allowed is False
        assert decision.reason_code == "OPERATION_ID_MISSING"
        with pytest.raises(AuthorizationError):
            guarded_dispatch("lab-target", operation_id, handler, document=_document())
    assert handler.calls == 0


@pytest.mark.parametrize(
    "operation_id",
    ["system.command.run", "web.shell.spawn", "generic.exec", "terminal.open", "run_command"],
)
def test_generic_execution_stays_forbidden(operation_id: str) -> None:
    document = _document(scope={"allowed_operations": [operation_id]})
    decision = authorize_operation("lab-target", operation_id, document=document)
    assert decision.allowed is False
    assert decision.reason_code == "GENERIC_EXECUTION_FORBIDDEN"

    handler = HandlerSpy()
    with pytest.raises(AuthorizationError):
        guarded_dispatch("lab-target", operation_id, handler, document=document)
    assert handler.calls == 0


def test_ambiguous_registry_with_duplicate_ids_fails_closed() -> None:
    document = _document()
    document["targets"].append(deepcopy(document["targets"][0]))
    decision = authorize_operation("lab-target", OFFENSIVE_OPERATION, document=document)
    assert decision.allowed is False
    assert decision.reason_code == "TARGET_REGISTRY_AMBIGUOUS"


def test_caller_cannot_self_declare_an_offensive_operation_as_safety() -> None:
    decision = authorize_operation(
        "lab-target",
        OFFENSIVE_OPERATION,
        document=_document(authorization_state="BLOCKED"),
        operation_class="SAFETY",
    )
    assert decision.allowed is False
    assert decision.reason_code == "OPERATION_CLASS_INVALID"


def test_invalid_operation_class_fails_closed() -> None:
    decision = authorize_operation(
        "lab-target",
        OFFENSIVE_OPERATION,
        document=_document(),
        operation_class="ANYTHING",
    )
    assert decision.allowed is False
    assert decision.reason_code == "OPERATION_CLASS_INVALID"


# --------------------------------------------------------------------------
# safety operations must never be blocked
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"authorization_state": "BLOCKED"},
        {"authorization_state": "UNVERIFIED"},
        {"lifecycle": "RETIRED"},
        {"health": "UNHEALTHY"},
        {"scope": {"allowed_operations": []}},
    ],
)
@pytest.mark.parametrize(
    "operation_id",
    ["lab.lifecycle.stop", "lab.lifecycle.reset", "lab.lifecycle.destroy", "lab.lifecycle.cleanup"],
)
def test_safety_operations_remain_available_on_denied_targets(
    overrides: dict,
    operation_id: str,
) -> None:
    document = _document(**overrides)
    decision = authorize_operation(operation_id and "lab-target", operation_id, document=document)
    assert decision.allowed is True
    assert decision.reason_code == "ALLOW_SAFETY_OPERATION"
    assert decision.operation_class == "SAFETY"

    handler = HandlerSpy()
    guarded_dispatch("lab-target", operation_id, handler, document=document)
    assert handler.calls == 1


def test_safety_operation_still_requires_a_canonical_target_id() -> None:
    handler = HandlerSpy()
    decision = authorize_operation(
        "http://lab-target:8080/", SAFETY_OPERATION, document=_document()
    )
    assert decision.allowed is False
    assert decision.reason_code == "TARGET_ID_NOT_CANONICAL"
    with pytest.raises(AuthorizationError):
        guarded_dispatch("http://lab-target:8080/", SAFETY_OPERATION, handler, document=_document())
    assert handler.calls == 0


def test_safety_operation_on_unknown_target_fails_closed() -> None:
    decision = authorize_operation("nope", SAFETY_OPERATION, document=_document())
    assert decision.allowed is False
    assert decision.reason_code == "TARGET_UNKNOWN"


# --------------------------------------------------------------------------
# audit-friendly decision object
# --------------------------------------------------------------------------


def test_decision_is_json_serializable_and_carries_stable_fields() -> None:
    decision = authorize_operation("lab-target", OFFENSIVE_OPERATION, document=_document())
    payload = json.loads(json.dumps(decision.as_dict(), sort_keys=True))
    assert set(payload) == {
        "target_id",
        "operation_id",
        "operation_class",
        "allowed",
        "reason_code",
        "authorization_state",
        "lifecycle",
        "health",
        "environment_id",
        "allowed_operations",
    }
    assert isinstance(payload["allowed"], bool)
    assert payload["reason_code"] in REASON_CODES


@pytest.mark.parametrize(
    ("label", "overrides", "target_id", "reason_code"),
    DENIAL_CASES,
    ids=[case[0] for case in DENIAL_CASES],
)
def test_decisions_never_leak_raw_network_locators(
    label: str,
    overrides: dict,
    target_id,
    reason_code: str,
) -> None:
    decision = authorize_operation(target_id, OFFENSIVE_OPERATION, document=_document(**overrides))
    serialized = json.dumps(decision.as_dict())
    assert "://" not in serialized, label
    assert "10.0.0.5" not in serialized, label
    assert "8080" not in serialized, label


def test_decision_rejects_locator_labels_by_construction() -> None:
    with pytest.raises(ValueError):
        AuthorizationDecision(
            target_id="http://lab-target/",
            operation_id=OFFENSIVE_OPERATION,
            allowed=False,
            reason_code="TARGET_UNKNOWN",
        )


def test_unknown_reason_code_is_rejected() -> None:
    with pytest.raises(ValueError):
        AuthorizationDecision(
            target_id="lab-target",
            operation_id=OFFENSIVE_OPERATION,
            allowed=False,
            reason_code="NOT_A_REASON",
        )


# --------------------------------------------------------------------------
# canonical registry integration + CLI
# --------------------------------------------------------------------------


def test_committed_registry_allows_a_known_lab_operation() -> None:
    decision = authorize_operation("juice-shop-web", "web_vulnerability_scan")
    assert decision.allowed is True
    assert decision.authorization_state == "LAB_ONLY"


def test_committed_registry_denies_an_out_of_scope_operation() -> None:
    decision = authorize_operation("webgoat-webwolf", "manual_exploitation")
    assert decision.allowed is False
    assert decision.reason_code == "OPERATION_OUT_OF_SCOPE"


def test_cli_exits_two_on_denial_and_zero_on_allow() -> None:
    allow = subprocess.run(
        [sys.executable, str(MODULE_PATH), "authorize", "juice-shop-web", "discovery"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert allow.returncode == 0
    assert json.loads(allow.stdout)["reason_code"] == "ALLOW_OFFENSIVE_OPERATION"

    deny = subprocess.run(
        [sys.executable, str(MODULE_PATH), "authorize", "http://juice-shop:3000/", "discovery"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert deny.returncode == 2
    assert json.loads(deny.stdout)["allowed"] is False
