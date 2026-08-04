"""Signal catalog, normalization, deterministic evaluator, and canonical mapping for the API pack."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from api_pentest_runbooks.adapter import extract_runner_meta

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_CATALOG_PATH = REPO_ROOT / "signals" / "signal-catalog.yaml"
MAPPING_PATH = REPO_ROOT / "signals" / "runbook-signal-mapping.yaml"


class SignalError(ValueError):
    """Raised when a signal contract is violated."""


class _MissingSignal:
    """Falsy, membership-safe placeholder for a known signal that was not provided.

    Keeps the historical semantics of an absent signal (comparable to ``False``)
    while making ``x in MISSING_SIGNAL`` return ``False`` instead of raising
    ``TypeError``. It is never emitted in evaluation results or evidence.
    """

    _instance: _MissingSignal | None = None

    def __new__(cls) -> _MissingSignal:  # noqa: PYI034
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __iter__(self) -> Any:
        return iter(())

    def __contains__(self, item: Any) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        if other is self:
            return True
        return other is False or other is None

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(False)

    def __repr__(self) -> str:
        return "MISSING_SIGNAL"


#: Singleton returned when a known signal is absent from the provided signals.
MISSING_SIGNAL = _MissingSignal()

#: Container types accepted on the right-hand side of ``in`` / ``not in``.
_MEMBERSHIP_TYPES = (str, bytes, dict, set, frozenset, list, tuple)


@dataclass(frozen=True)
class SignalDefinition:
    name: str
    type: str
    family: str
    producer: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class EvaluationResult:
    decision: str
    reasons: tuple[str, ...] = ()
    evaluated: tuple[str, ...] = ()


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


class _Evaluator(ast.NodeVisitor):
    def __init__(self, signals: dict[str, Any]) -> None:
        self.signals = signals

    def visit(self, node: ast.AST) -> Any:  # type: ignore[override]
        return super().visit(node)

    def visit_Set(self, node: ast.Set) -> Any:  # type: ignore[override]
        return {self.visit(element) for element in node.elts}

    def visit_List(self, node: ast.List) -> Any:  # type: ignore[override]
        return [self.visit(element) for element in node.elts]

    def _resolve_name(self, name: str) -> Any:
        if name in self.signals:
            return self.signals[name]
        return MISSING_SIGNAL

    def visit_Expression(self, node: ast.Expression) -> Any:  # type: ignore[override]
        return self.visit(node.body)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:  # type: ignore[override]
        values = [self.visit(value) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise SignalError("unsupported boolean operator")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:  # type: ignore[override]
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        raise SignalError("unsupported unary operator")

    @staticmethod
    def _membership(left: Any, right: Any) -> bool:
        if right is MISSING_SIGNAL:
            return False
        if isinstance(right, bool) or not isinstance(right, _MEMBERSHIP_TYPES):
            raise SignalError(
                f"membership test requires a container signal, got {type(right).__name__}"
            )
        if isinstance(right, (str, bytes)) and left is MISSING_SIGNAL:
            return False
        try:
            return left in right
        except TypeError as exc:  # unhashable or incompatible element type
            raise SignalError(f"unsupported membership operand: {exc}") from exc

    def visit_Compare(self, node: ast.Compare) -> Any:  # type: ignore[override]
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                if left != right:
                    return False
            elif isinstance(op, ast.NotEq):
                if left == right:
                    return False
            elif isinstance(op, ast.In):
                if not self._membership(left, right):
                    return False
            elif isinstance(op, ast.NotIn):
                if self._membership(left, right):
                    return False
            elif isinstance(op, ast.Is):
                if left is not right:
                    return False
            elif isinstance(op, ast.IsNot):
                if left is right:
                    return False
            else:
                raise SignalError(f"unsupported comparator {op.__class__.__name__}")
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:  # type: ignore[override]
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "startswith":
            raise SignalError("only startswith() calls are supported")
        value = self.visit(node.func.value)
        prefix = self.visit(node.args[0])
        return isinstance(value, str) and value.startswith(prefix)

    def visit_Constant(self, node: ast.Constant) -> Any:  # type: ignore[override]
        return node.value

    def visit_Attribute(self, node: ast.Attribute) -> Any:  # type: ignore[override]
        dotted = _dotted(node)
        if dotted in self.signals:
            return self.signals[dotted]
        value = self.visit(node.value)
        if not isinstance(value, dict) or node.attr not in value:
            raise SignalError(f"unknown signal path {ast.dump(node)}")
        return value[node.attr]

    def visit_Name(self, node: ast.Name) -> Any:  # type: ignore[override]
        if node.id in {"true", "false", "True", "False"}:
            return node.id in {"true", "True"}
        return self._resolve_name(node.id)


#: Dotted aliases historically emitted by the JWT/TLS normalizers.
#: Each alias maps to an already existing canonical signal in the catalog.
#: Aliases add no new vocabulary: unknown signals stay rejected.
SIGNAL_ALIASES: dict[str, str] = {
    "jwt.alg": "jwt_alg",
    "jwt.claims.aud": "jwt_claims_aud",
    "jwt.claims.exp": "jwt_claims_exp",
    "jwt.claims.iss": "jwt_claims_iss",
    "jwt.claims.sub": "jwt_claims_sub",
    "jwt.secret_bits": "jwt_secret_bits",
    "jwt.signature.valid": "jwt_signature_valid",
    "tls.cert_expired": "tls_cert_expired",
    "tls.hostname_mismatch": "tls_hostname_mismatch",
    "tls.plaintext_allowed": "tls_plaintext_allowed",
    "tls.weak_ciphers": "tls_weak_ciphers",
}


def canonical_signal_name(name: str) -> str:
    """Return the canonical catalog name for a signal alias, else the name itself."""
    return SIGNAL_ALIASES.get(name, name)


def canonicalize_signals(signals: dict[str, Any]) -> dict[str, Any]:
    """Remap known dotted aliases onto canonical catalog signals."""
    canonical: dict[str, Any] = {}
    for key, value in signals.items():
        canonical[canonical_signal_name(key)] = value
    return canonical


def _produced_signals_from_expr(expr: str) -> list[str]:
    found: list[str] = []
    for signal in _load_signal_catalog():
        if signal in expr:
            found.append(signal)
    return found


def _canonicalize_expression(expr: str) -> str:
    canonical = expr
    for alias in sorted(SIGNAL_ALIASES, key=len, reverse=True):
        canonical = canonical.replace(alias, SIGNAL_ALIASES[alias])
    return canonical


def _canonicalize_criteria(criteria: dict[str, list[str]]) -> dict[str, list[str]]:
    canonical: dict[str, list[str]] = dict(criteria)
    for key in ("vulnerable_when", "secure_when", "inconclusive_when"):
        canonical[key] = [_canonicalize_expression(expr) for expr in criteria.get(key, [])]
    return canonical


def _infer_signals_from_criteria(criteria: dict[str, list[str]]) -> set[str]:
    catalog = set(_load_signal_catalog())
    inferred: set[str] = set(catalog)
    for key in ("vulnerable_when", "secure_when", "inconclusive_when"):
        for expr in criteria.get(key, []):
            inferred.update(_produced_signals_from_expr(expr))
    return inferred


def evaluate_signals(signals: dict[str, Any], criteria: dict[str, list[str]]) -> EvaluationResult:
    signals = canonicalize_signals(signals)
    criteria = _canonicalize_criteria(criteria)
    explicit = _infer_signals_from_criteria(criteria)
    unknown_provided = sorted(set(signals) - explicit)
    if unknown_provided:
        raise SignalError(f"unknown signals: {', '.join(unknown_provided)}")
    catalog = _load_signal_catalog()
    for name, value in signals.items():
        expected = catalog[name].type if name in catalog else "string"
        if expected.startswith("map[") and not isinstance(value, dict):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
        if expected == "integer" and not isinstance(value, int):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
        if expected == "boolean" and not isinstance(value, bool):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
        if expected == "string" and value is not None and not isinstance(value, str):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
    evaluator = _Evaluator(signals)
    evaluated: list[str] = []
    reasons: list[str] = []
    for expr in criteria.get("vulnerable_when", []):
        evaluated.append(expr)
        if ast.parse(expr, mode="eval") and evaluator.visit(ast.parse(expr, mode="eval").body):
            reasons.append(f"vulnerable:{expr}")
            return EvaluationResult(decision="vulnerable", reasons=tuple(reasons), evaluated=tuple(evaluated))
    for expr in criteria.get("secure_when", []):
        evaluated.append(expr)
        if ast.parse(expr, mode="eval") and evaluator.visit(ast.parse(expr, mode="eval").body):
            reasons.append(f"secure:{expr}")
            return EvaluationResult(decision="secure", reasons=tuple(reasons), evaluated=tuple(evaluated))
    for expr in criteria.get("inconclusive_when", []):
        evaluated.append(expr)
        if ast.parse(expr, mode="eval") and evaluator.visit(ast.parse(expr, mode="eval").body):
            reasons.append(f"inconclusive:{expr}")
            return EvaluationResult(decision="inconclusive", reasons=tuple(reasons), evaluated=tuple(evaluated))
    return EvaluationResult(decision="inconclusive", reasons=("no criteria matched",), evaluated=tuple(evaluated))


def _load_signal_catalog() -> dict[str, SignalDefinition]:
    data = yaml.safe_load(SIGNAL_CATALOG_PATH.read_text(encoding="utf-8"))
    signals = {}
    for key, value in (data.get("signals") or {}).items():
        signals[key] = SignalDefinition(
            name=str(value.get("name") or key),
            type=str(value.get("type") or "string"),
            family=str(value.get("family") or "runtime"),
            producer=tuple(value.get("producer") or []),
            description=str(value.get("description") or ""),
        )
    return signals


_RUNNER_META_KEYS = {"runner_exit_code", "runner_status", "runner_stdout"}


def _normalize_http_response(response: dict[str, Any]) -> dict[str, Any]:
    headers = response.get("headers") or response.get("response_headers") or {}
    return {
        "response_status": response.get("status_code") or response.get("response_status"),
        "response_headers": {str(k): str(v) for k, v in headers.items()},
        "response_body_sample": response.get("body_sample") or response.get("redacted_response_sample") or "",
        "response_contains_sensitive_data": bool(response.get("contains_sensitive_data", False)),
        "target_reachable": True,
        "prerequisites_missing": False,
    }


def _normalize_request_meta(request_meta: dict[str, Any]) -> dict[str, Any]:
    redirect_target = ""
    if isinstance(request_meta, dict):
        redirect_target = str(request_meta.get("final_url") or request_meta.get("redirect_target") or "")
    return {"request_redirect_target": redirect_target}


def _normalize_auth(auth_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(auth_payload, dict):
        return {"auth_accepted": False, "auth_scheme": ""}
    return {
        "auth_accepted": bool(auth_payload.get("accepted", False)),
        "auth_scheme": str(auth_payload.get("scheme") or ""),
    }


def _normalize_jwt(jwt_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(jwt_payload, dict):
        return {
            "jwt.claims.aud": None,
            "jwt.claims.exp": None,
            "jwt.claims.iss": None,
            "jwt.claims.sub": None,
            "jwt.alg": "",
            "jwt.secret_bits": 0,
            "jwt.signature.valid": False,
        }
    claims = jwt_payload.get("claims") or {}
    return {
        "jwt.claims.aud": claims.get("aud"),
        "jwt.claims.exp": claims.get("exp"),
        "jwt.claims.iss": claims.get("iss"),
        "jwt.claims.sub": claims.get("sub"),
        "jwt.alg": str(jwt_payload.get("alg") or ""),
        "jwt.secret_bits": int(jwt_payload.get("secret_bits") or 0),
        "jwt.signature.valid": bool(jwt_payload.get("signature_valid", False)),
    }


def _normalize_upload(upload_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(upload_payload, dict):
        return {"upload_executed": False}
    return {"upload_executed": bool(upload_payload.get("executed", False))}


def _normalize_workflow(workflow_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workflow_payload, dict):
        return {"workflow_status": ""}
    return {"workflow_status": str(workflow_payload.get("status") or "")}


def _normalize_rate(rate_payload: dict[str, Any] | None) -> dict[str, Any]:
    return {"rate_limit.triggered": bool((rate_payload or {}).get("triggered", False))}


def _normalize_authorization(authz_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(authz_payload, dict):
        return {"object.owner_id": "", "subject.id": ""}
    return {
        "object.owner_id": str(authz_payload.get("object_owner_id") or authz_payload.get("object.owner_id") or ""),
        "subject.id": str(authz_payload.get("subject_id") or authz_payload.get("subject.id") or ""),
    }


def _normalize_business_logic(logic_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(logic_payload, dict):
        return {"entity.id": "", "entity.owner_id": ""}
    return {
        "entity.id": str(logic_payload.get("entity_id") or logic_payload.get("entity.id") or ""),
        "entity.owner_id": str(logic_payload.get("entity_owner_id") or logic_payload.get("entity.owner_id") or ""),
    }


def _normalize_discovery(discovery_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(discovery_payload, dict):
        return {"response_contains_schema": False, "openapi_security_schemes_present": False}
    return {
        "response_contains_schema": bool(discovery_payload.get("schema_found", False)),
        "openapi_security_schemes_present": bool(discovery_payload.get("security_schemes_present", False)),
    }


def _normalize_tls(tls_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tls_payload, dict):
        return {
            "tls.cert_expired": False,
            "tls.hostname_mismatch": False,
            "tls.weak_ciphers": False,
            "tls.plaintext_allowed": False,
        }
    return {
        "tls.cert_expired": bool(tls_payload.get("cert_expired", False)),
        "tls.hostname_mismatch": bool(tls_payload.get("hostname_mismatch", False)),
        "tls.weak_ciphers": bool(tls_payload.get("weak_ciphers", False)),
        "tls.plaintext_allowed": bool(tls_payload.get("plaintext_allowed", False)),
    }


def _normalize_handler_output(handler: str, output: dict[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if not isinstance(output, dict):
        return normalized
    if handler in {"http", "openapi", "workflow", "headers", "race"}:
        normalized.update(_normalize_http_response(output))
        request_meta = output.get("request_metadata") or output.get("request") or {}
        normalized.update(_normalize_request_meta(request_meta))
        normalized.update(_normalize_auth(output.get("auth") or output.get("auth_result")))
        normalized.update(_normalize_upload(output.get("upload") or output.get("upload_result")))
        normalized.update(_normalize_rate(output.get("rate_limit") or output.get("rate")))
        normalized.update(_normalize_authorization(output.get("authorization") or output.get("authz")))
        normalized.update(_normalize_business_logic(output.get("business_logic") or output.get("logic")))
        normalized.update(_normalize_discovery(output.get("discovery")))
        return normalized
    if handler == "jwt":
        normalized.update(_normalize_jwt(output.get("jwt") or output))
        return normalized
    if handler == "tls":
        normalized.update(_normalize_tls(output))
        return normalized
    if handler in {"workflow", "race"}:
        normalized.update(_normalize_workflow(output.get("workflow") or output))
        return normalized
    return normalized


def normalize_execution_output(handler: str, output: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(output, dict):
        output = {}
    functional = {
        "target_reachable": bool(output.get("target_reachable", True)),
        "prerequisites_missing": bool(output.get("prerequisites_missing", False)),
        "handler_signal": str(output.get("finding") or output.get("status") or ""),
    }
    if output.get("status") == "error":
        functional["prerequisites_missing"] = True
    for source, target in (
        (("status_code",), "response_status"),
        (("response_headers",), "headers"),
        (("redacted_response_sample", "body_sample"), "response_body_sample"),
        (("contains_sensitive_data",), "response_contains_sensitive_data"),
        (("schema_found",), "response_contains_schema"),
        (("security_schemes_present",), "openapi_security_schemes_present"),
    ):
        for key in source:
            if key in output:
                functional[target] = output[key]
                break
    request_meta = output.get("request_metadata") or output.get("request") or {}
    functional["request_redirect_target"] = str(request_meta.get("final_url") or request_meta.get("redirect_target") or "")
    functional.update(_normalize_auth(output.get("auth") or output.get("auth_result")))
    functional.update(_normalize_upload(output.get("upload") or output.get("upload_result")))
    functional.update(_normalize_rate(output.get("rate_limit") or output.get("rate")))
    functional.update(_normalize_authorization(output.get("authorization") or output.get("authz")))
    functional.update(_normalize_business_logic(output.get("business_logic") or output.get("logic")))
    jwt_payload = output.get("jwt") or output
    functional.update(_normalize_jwt(jwt_payload))
    functional.update(_normalize_tls(output))
    functional.update(_normalize_workflow(output.get("workflow") or output))
    # Absent signals (None) are not emitted: an absent claim is not a functional signal.
    return canonicalize_signals(
        {
            key: value
            for key, value in functional.items()
            if key not in _RUNNER_META_KEYS and value is not None
        }
    )


def load_signal_catalog() -> dict[str, SignalDefinition]:
    return _load_signal_catalog()


def load_canonical_mapping() -> dict[str, dict[str, Any]]:
    if not MAPPING_PATH.exists():
        return {}
    data = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))
    return {str(item.get("runbook_id")): item for item in (data.get("mappings") or []) if item.get("runbook_id")}


__all__ = [
    "SIGNAL_ALIASES",
    "EvaluationResult",
    "SignalDefinition",
    "SignalError",
    "canonical_signal_name",
    "canonicalize_signals",
    "evaluate_signals",
    "extract_runner_meta",
    "load_canonical_mapping",
    "load_signal_catalog",
    "normalize_execution_output",
]
