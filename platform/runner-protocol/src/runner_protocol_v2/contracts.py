"""Canonical Runner Protocol v2 validation and deterministic contract helpers.

Protocol validation helpers are side-effect free. Optional SDK enforcement primitives
provide durable idempotency and bounded POSIX process supervision, but never authorize work.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

RETRYABLE_CODES = frozenset(
    {"TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE", "TIMEOUT_SOFT"}
)
FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "cookie",
        "authorization",
        "api_key",
        "credential",
        "private_key",
    }
)
EXPECTED_RUNNER_FAMILIES = frozenset({"api", "devsecops", "ai-mcp"})


class ProtocolValidationError(ValueError):
    """Raised when a message or repository contract violates Runner Protocol v2."""


def contract_root() -> Path:
    """Resolve the canonical contract root without silently inventing a fallback.

    Editable repository use resolves from the SDK source tree. A non-editable consumer
    must set ``RUNNER_PROTOCOL_CONTRACT_ROOT`` to a directory containing the canonical
    ``schemas/`` and ``compatibility.yaml`` artefacts.
    """
    configured = os.environ.get("RUNNER_PROTOCOL_CONTRACT_ROOT")
    candidate = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[2]
    )
    required = (
        candidate / "schemas" / "runner-protocol-v2.schema.json",
        candidate / "schemas" / "conformance-report.schema.json",
        candidate / "compatibility.yaml",
    )
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        source = "RUNNER_PROTOCOL_CONTRACT_ROOT" if configured else "SDK source location"
        raise ProtocolValidationError(
            f"canonical contract root from {source} is incomplete: {sorted(missing)}"
        )
    return candidate


def load_schema() -> dict[str, Any]:
    """Load and validate the canonical protocol JSON Schema."""
    path = contract_root() / "schemas" / "runner-protocol-v2.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load_schema(), format_checker=jsonschema.FormatChecker()
    )


def _format_path(path: Iterable[Any]) -> str:
    parts = [str(part) for part in path]
    return ".".join(parts) if parts else "<root>"


def _leaf_errors(
    error: jsonschema.ValidationError,
) -> Iterable[jsonschema.ValidationError]:
    """Yield actionable leaf errors instead of an opaque ``oneOf`` summary."""
    if error.context:
        for child in error.context:
            yield from _leaf_errors(child)
        return
    yield error


def validate_schema(message: Mapping[str, Any]) -> None:
    """Validate one protocol message against the canonical schema bundle."""
    root_errors = _validator().iter_errors(message)
    errors = [leaf for root_error in root_errors for leaf in _leaf_errors(root_error)]
    if errors:
        diagnostics = {
            (_format_path(error.absolute_path), error.message) for error in errors
        }
        details = "; ".join(
            f"{path}: {message}" for path, message in sorted(diagnostics)
        )
        raise ProtocolValidationError(details)


def _walk_forbidden_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_SECRET_KEYS:
                location = ".".join((*path, str(key)))
                raise ProtocolValidationError(
                    f"raw secret field {location!r} is forbidden; use a secret reference"
                )
            _walk_forbidden_keys(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden_keys(child, (*path, str(index)))


def _parse_time(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolValidationError(f"{field} is not a valid RFC 3339 timestamp") from exc


def _validate_error(error: Mapping[str, Any]) -> None:
    code = str(error["code"])
    retryable = bool(error["retryable"])
    expected = code in RETRYABLE_CODES
    if retryable != expected:
        raise ProtocolValidationError(
            f"error {code} retryable={retryable} conflicts with the stable taxonomy"
        )
    _walk_forbidden_keys(error, ("error",))


def validate_semantics(message: Mapping[str, Any]) -> None:
    """Validate invariants that JSON Schema cannot express safely."""
    validate_schema(message)
    _walk_forbidden_keys(message)

    message_type = message["message_type"]
    if message_type == "runner.step.request":
        budget = message["timeout_budget"]
        soft = int(budget["soft_timeout_ms"])
        hard = int(budget["hard_timeout_ms"])
        grace = int(message["cancellation_policy"]["grace_period_ms"])
        if hard <= soft:
            raise ProtocolValidationError(
                "hard_timeout_ms must be greater than soft_timeout_ms"
            )
        if grace > hard:
            raise ProtocolValidationError(
                "grace_period_ms must fit inside the hard timeout budget"
            )

    error = message.get("error")
    if isinstance(error, Mapping):
        _validate_error(error)

    if message_type == "runner.outcome":
        started = _parse_time(str(message["started_at"]), "started_at")
        finished = _parse_time(str(message["finished_at"]), "finished_at")
        if finished < started:
            raise ProtocolValidationError("finished_at cannot precede started_at")

        status = message["status"]
        if status == "TIMED_OUT" and message["error"]["code"] != "TIMEOUT_HARD":
            raise ProtocolValidationError(
                "TIMED_OUT outcomes must use the TIMEOUT_HARD error code"
            )
        if status == "REFUSED" and message["error"]["category"] not in {
            "validation",
            "compatibility",
            "authorization",
            "conflict",
        }:
            raise ProtocolValidationError(
                "REFUSED outcomes require a pre-execution refusal category"
            )


def request_fingerprint(request: Mapping[str, Any]) -> str:
    """Return the canonical fingerprint for one logical step effect.

    ``attempt_id``, ``emitted_at`` and the idempotency key itself are excluded so a
    retry of the same logical step retains the same fingerprint.
    """
    validate_semantics(request)
    if request["message_type"] != "runner.step.request":
        raise ProtocolValidationError("fingerprints apply only to runner.step.request")

    correlation = request["correlation"]
    canonical = {
        "protocol_major": str(request["protocol_version"]).split(".", 1)[0],
        "campaign_id": correlation["campaign_id"],
        "run_id": correlation["run_id"],
        "step_id": correlation["step_id"],
        "authorization_ref": request["authorization_ref"],
        "operation": request["operation"],
        "timeout_budget": request["timeout_budget"],
        "retry_policy": request["retry_policy"],
        "cancellation_policy": request["cancellation_policy"],
        "progress_mode": request.get("progress_mode", "optional"),
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_idempotency(
    existing_fingerprint: str | None, request: Mapping[str, Any]
) -> str:
    """Classify a request without executing it or mutating a replay ledger."""
    candidate = request_fingerprint(request)
    if existing_fingerprint is None:
        return "NEW"
    if existing_fingerprint == candidate:
        return "REPLAY_SAME"
    return "IDEMPOTENCY_CONFLICT"


def validate_progress_sequence(events: Iterable[Mapping[str, Any]]) -> None:
    """Validate one attempt's ordered progress stream."""
    expected_correlation: Mapping[str, Any] | None = None
    previous_sequence = 0
    previous_percent = 0.0

    for event in events:
        validate_semantics(event)
        if event["message_type"] != "runner.progress":
            raise ProtocolValidationError("progress stream contains a non-progress message")
        correlation = event["correlation"]
        if expected_correlation is None:
            expected_correlation = correlation
        elif correlation != expected_correlation:
            raise ProtocolValidationError(
                "all progress events must belong to the same correlation tuple"
            )

        sequence = int(event["sequence"])
        if sequence <= previous_sequence:
            raise ProtocolValidationError("progress sequence must increase strictly")
        previous_sequence = sequence

        if "percent" in event:
            percent = float(event["percent"])
            if percent < previous_percent:
                raise ProtocolValidationError("progress percent cannot decrease")
            previous_percent = percent


def _validate_candidate_adapter(
    repository_root: Path,
    *,
    relative_path: str,
    required_arguments: tuple[str, ...],
    candidate_name: str,
) -> None:
    adapter_path = (repository_root / relative_path).resolve()
    if repository_root not in adapter_path.parents or not adapter_path.is_file():
        raise ProtocolValidationError(
            f"{candidate_name} path is missing or outside repository"
        )
    adapter_source = adapter_path.read_text(encoding="utf-8")
    for forbidden in ("execute_runbook", "execute_command"):
        if forbidden in adapter_source:
            raise ProtocolValidationError(
                f"{candidate_name} must not reference {forbidden}"
            )
    for argument in required_arguments:
        if argument not in adapter_source:
            raise ProtocolValidationError(
                f"{candidate_name} activation argument {argument!r} is not enforced"
            )


def _validate_synthetic_worker(
    repository_root: Path,
    *,
    relative_path: str,
    family_name: str,
) -> None:
    worker_path = (repository_root / relative_path).resolve()
    if repository_root not in worker_path.parents or not worker_path.is_file():
        raise ProtocolValidationError(
            f"{family_name} supervised synthetic worker path is missing or outside repository"
        )
    worker_source = worker_path.read_text(encoding="utf-8")
    for forbidden in (
        "socket",
        "requests",
        "urllib",
        "execute_runbook",
        "execute_command",
    ):
        if forbidden in worker_source:
            raise ProtocolValidationError(
                f"{family_name} supervised synthetic worker must not reference {forbidden}"
            )


def validate_compatibility_matrix() -> None:
    """Validate the compatibility and conformance declaration."""
    root = contract_root()
    data = yaml.safe_load((root / "compatibility.yaml").read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.3":
        raise ProtocolValidationError("compatibility schema version must be 1.3")
    if data["protocol"] != {
        "name": "runner-protocol",
        "version": "2.0.0",
        "status": "contract_only",
    }:
        raise ProtocolValidationError("compatibility protocol identity is inconsistent")

    rules = data["compatibility_rules"]
    required_rules = {
        "major_version": "exact_match",
        "unknown_major": "fail_closed",
        "unknown_message_type": "fail_closed",
        "invalid_schema": "fail_closed",
        "terminal_outcome": "mandatory",
        "terminal_evidence_reference": "mandatory",
        "authorization_source": "hermes_control_plane",
    }
    for key, expected in required_rules.items():
        if rules.get(key) != expected:
            raise ProtocolValidationError(
                f"compatibility rule {key!r} must be {expected!r}"
            )

    kit = data.get("conformance_kit")
    expected_kit = {
        "status": "available",
        "transport": "json_lines",
        "execution_model": "isolated_candidate_process",
        "reference_adapter": "test_only",
        "report_schema": "schemas/conformance-report.schema.json",
        "promotion_effect": "none",
        "required_verdict_for_promotion": "PASS",
    }
    if kit != expected_kit:
        raise ProtocolValidationError("conformance kit declaration is inconsistent")

    report_schema_path = root / str(kit["report_schema"])
    if not report_schema_path.is_file():
        raise ProtocolValidationError("conformance report schema is missing")
    report_schema = json.loads(report_schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(report_schema)

    migration_gates = data.get("migration_gates")
    required_gates = {
        "schema_validation",
        "semantic_validation",
        "correlation_propagation",
        "idempotency_replay_test",
        "cancellation_timeout_test",
        "evidence_reference_test",
        "secret_redaction_test",
        "conformance_report_pass",
        "human_review_before_promotion",
    }
    if not isinstance(migration_gates, list) or len(migration_gates) != len(
        set(migration_gates)
    ):
        raise ProtocolValidationError("migration gates must be a unique list")
    if set(migration_gates) != required_gates:
        raise ProtocolValidationError("migration gate inventory is incomplete or unexpected")

    families = data["runner_families"]
    if not isinstance(families, list):
        raise ProtocolValidationError("runner family inventory must be a list")
    ids = [family.get("id") for family in families]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_RUNNER_FAMILIES:
        raise ProtocolValidationError(
            f"runner family inventory mismatch: {sorted(str(value) for value in ids)}"
        )
    by_id = {family["id"]: family for family in families}

    api_expected = {
        "implementation_status": "candidate",
        "protocol_status": "conformance_only",
        "conformance": "PASS_SYNTHETIC",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "supported_scope": "synthetic_conformance_only",
        "activation": "explicit_flag",
        "adapter_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "runner_protocol_adapter.py"
        ),
        "activation_argument": "--conformance-only",
    }
    api = by_id["api"]
    for key, expected in api_expected.items():
        if api.get(key) != expected:
            raise ProtocolValidationError(
                f"API candidate field {key!r} must be {expected!r}"
            )

    durable_expected = {
        "status": "PASS_SYNTHETIC",
        "integration_scope": "synthetic_conformance_only",
        "adapter_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "durable_runner_protocol_adapter.py"
        ),
        "activation_argument": "--durable-ledger",
        "storage_requirement": "absolute_path_outside_working_tree",
        "restart_replay": "PASS_SYNTHETIC",
        "abandoned_claim_reclaim": "blocked",
        "production_effect_claim": "none",
    }
    if api.get("durable_idempotency") != durable_expected:
        raise ProtocolValidationError(
            "API durable-idempotency declaration is inconsistent"
        )

    api_supervised_expected = {
        "status": "PASS_SYNTHETIC_PROCESS",
        "integration_scope": "fixed_synthetic_worker_only",
        "adapter_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "supervised_runner_protocol_adapter.py"
        ),
        "worker_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "synthetic_supervised_worker.py"
        ),
        "activation_arguments": [
            "--conformance-only",
            "--synthetic-process-only",
            "--durable-ledger",
        ],
        "durable_claim_before_spawn": "PASS_SYNTHETIC_PROCESS",
        "async_cancellation": "PASS_SYNTHETIC_PROCESS",
        "hard_timeout": "PASS_SYNTHETIC_PROCESS",
        "descendant_residue": "fail_closed_inconclusive",
        "raw_output_persistence": "none",
        "sandbox_status": "NOT_IMPLEMENTED",
        "production_effect_claim": "none",
    }
    if api.get("supervised_process") != api_supervised_expected:
        raise ProtocolValidationError(
            "API supervised-process declaration is inconsistent"
        )

    devsecops_expected = {
        "implementation_status": "candidate",
        "protocol_status": "conformance_only",
        "conformance": "PASS_SYNTHETIC_PROCESS",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "supported_scope": "fixed_synthetic_worker_only",
        "activation": "explicit_flag",
        "adapter_path": (
            "security/packs/devsecops/src/devsecops_runbooks/"
            "supervised_runner_protocol_adapter.py"
        ),
        "activation_argument": "--conformance-only",
    }
    devsecops = by_id["devsecops"]
    for key, expected in devsecops_expected.items():
        if devsecops.get(key) != expected:
            raise ProtocolValidationError(
                f"DevSecOps candidate field {key!r} must be {expected!r}"
            )

    devsecops_supervised_expected = {
        "status": "PASS_SYNTHETIC_PROCESS",
        "integration_scope": "fixed_synthetic_worker_only",
        "adapter_path": (
            "security/packs/devsecops/src/devsecops_runbooks/"
            "supervised_runner_protocol_adapter.py"
        ),
        "worker_path": (
            "security/packs/devsecops/src/devsecops_runbooks/"
            "synthetic_supervised_worker.py"
        ),
        "activation_arguments": [
            "--conformance-only",
            "--synthetic-process-only",
            "--durable-ledger",
        ],
        "durable_claim_before_spawn": "PASS_SYNTHETIC_PROCESS",
        "async_cancellation": "PASS_SYNTHETIC_PROCESS",
        "hard_timeout": "PASS_SYNTHETIC_PROCESS",
        "descendant_residue": "fail_closed_inconclusive",
        "raw_output_persistence": "none",
        "sandbox_status": "NOT_IMPLEMENTED",
        "production_effect_claim": "none",
    }
    if devsecops.get("supervised_process") != devsecops_supervised_expected:
        raise ProtocolValidationError(
            "DevSecOps supervised-process declaration is inconsistent"
        )

    repository_root = root.parents[1]
    candidate_declarations = (
        (
            str(api["adapter_path"]),
            (str(api["activation_argument"]),),
            "API conformance candidate",
        ),
        (
            str(durable_expected["adapter_path"]),
            ("--conformance-only", str(durable_expected["activation_argument"])),
            "API durable conformance candidate",
        ),
        (
            str(api_supervised_expected["adapter_path"]),
            tuple(str(value) for value in api_supervised_expected["activation_arguments"]),
            "API supervised synthetic-process candidate",
        ),
        (
            str(devsecops_supervised_expected["adapter_path"]),
            tuple(
                str(value)
                for value in devsecops_supervised_expected["activation_arguments"]
            ),
            "DevSecOps supervised synthetic-process candidate",
        ),
    )
    for relative_path, required_arguments, candidate_name in candidate_declarations:
        _validate_candidate_adapter(
            repository_root,
            relative_path=relative_path,
            required_arguments=required_arguments,
            candidate_name=candidate_name,
        )

    _validate_synthetic_worker(
        repository_root,
        relative_path=str(api_supervised_expected["worker_path"]),
        family_name="API",
    )
    _validate_synthetic_worker(
        repository_root,
        relative_path=str(devsecops_supervised_expected["worker_path"]),
        family_name="DevSecOps",
    )

    ai_mcp_expected = {
        "implementation_status": "not_started",
        "protocol_status": "contract_only",
        "conformance": "NOT_RUN",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "supported_scope": "none",
        "activation": "none",
        "adapter_path": None,
        "activation_argument": None,
    }
    ai_mcp = by_id["ai-mcp"]
    for key, expected in ai_mcp_expected.items():
        if ai_mcp.get(key) != expected:
            raise ProtocolValidationError(
                f"ai-mcp field {key!r} must remain {expected!r}"
            )

    if data["runtime_declaration"] != "NO_RUNTIME_CHANGE":
        raise ProtocolValidationError("runtime declaration must be NO_RUNTIME_CHANGE")
