"""Signal catalog, normalization, deterministic evaluator, and canonical mapping for the API pack."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_CATALOG_PATH = REPO_ROOT / "signals" / "signal-catalog.yaml"
MAPPING_PATH = REPO_ROOT / "signals" / "runbook-signal-mapping.yaml"


class SignalError(ValueError):
    """Raised when a signal contract is violated."""


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


class _Evaluator(ast.NodeVisitor):
    def __init__(self, signals: Dict[str, Any]) -> None:
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
        return False

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

    def visit_Compare(self, node: ast.Compare) -> Any:  # type: ignore[override]
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                if not left == right:
                    return False
            elif isinstance(op, ast.NotEq):
                if not left != right:
                    return False
            elif isinstance(op, ast.In):
                if left not in right:
                    return False
            elif isinstance(op, ast.NotIn):
                if left in right:
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
        value = self.visit(node.value)
        if not isinstance(value, dict) or node.attr not in value:
            raise SignalError(f"unknown signal path {ast.dump(node)}")
        return value[node.attr]

    def visit_Name(self, node: ast.Name) -> Any:  # type: ignore[override]
        if node.id in {"true", "false", "True", "False"}:
            return node.id in {"true", "True"}
        return self._resolve_name(node.id)


def _produced_signals_from_expr(expr: str) -> list[str]:
    found: list[str] = []
    for signal in _load_signal_catalog():
        if signal in expr:
            found.append(signal)
    return found


def _infer_signals_from_criteria(criteria: Dict[str, List[str]]) -> set[str]:
    catalog = set(_load_signal_catalog())
    inferred: set[str] = set(catalog)
    for key in ("vulnerable_when", "secure_when", "inconclusive_when"):
        for expr in criteria.get(key, []):
            inferred.update(_produced_signals_from_expr(expr))
    return inferred


def evaluate_signals(signals: Dict[str, Any], criteria: Dict[str, List[str]]) -> EvaluationResult:
    explicit = _infer_signals_from_criteria(criteria)
    unknown_provided = sorted(set(signals) - explicit)
    if unknown_provided:
        raise SignalError(f"unknown signals: {', '.join(unknown_provided)}")
    catalog = _load_signal_catalog()
    for name, value in signals.items():
        expected = catalog[name].type if name in catalog else "string"
        if expected == "integer" and not isinstance(value, int):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
        if expected == "boolean" and not isinstance(value, bool):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
        if expected == "string" and value is not None and not isinstance(value, str):
            raise SignalError(f"type mismatch: {name} expected {expected}, got {type(value).__name__}")
    evaluator = _Evaluator(signals)
    evaluated: List[str] = []
    reasons: List[str] = []
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


def _load_signal_catalog() -> Dict[str, SignalDefinition]:
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


def _normalize_http_response(response: Dict[str, Any]) -> Dict[str, Any]:
    headers = response.get("headers") or response.get("response_headers") or {}
    return {
        "response_status": response.get("status_code") or response.get("response_status"),
        "response_headers": {str(k): str(v) for k, v in headers.items()},
        "response_body_sample": response.get("body_sample") or response.get("redacted_response_sample") or "",
        "response_contains_sensitive_data": bool(response.get("contains_sensitive_data", False)),
        "target_reachable": True,
        "prerequisites_missing": False,
    }


def _normalize_request_meta(request_meta: Dict[str, Any]) -> Dict[str, Any]:
    redirect_target = ""
    if isinstance(request_meta, dict):
        redirect_target = str(request_meta.get("final_url") or request_meta.get("redirect_target") or "")
    return {"request_redirect_target": redirect_target}


def _normalize_auth(auth_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(auth_payload, dict):
        return {"auth_accepted": False, "auth_scheme": ""}
    return {
        "auth_accepted": bool(auth_payload.get("accepted", False)),
        "auth_scheme": str(auth_payload.get("scheme") or ""),
    }


def _normalize_jwt(jwt_payload: Dict[str, Any] | None) -> Dict[str, Any]:
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


def _normalize_upload(upload_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(upload_payload, dict):
        return {"upload_executed": False}
    return {"upload_executed": bool(upload_payload.get("executed", False))}


def _normalize_workflow(workflow_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(workflow_payload, dict):
        return {"workflow_status": ""}
    return {"workflow_status": str(workflow_payload.get("status") or "")}


def _normalize_rate(rate_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    return {"rate_limit.triggered": bool((rate_payload or {}).get("triggered", False))}


def _normalize_authorization(authz_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(authz_payload, dict):
        return {"object.owner_id": "", "subject.id": ""}
    return {
        "object.owner_id": str(authz_payload.get("object_owner_id") or authz_payload.get("object.owner_id") or ""),
        "subject.id": str(authz_payload.get("subject_id") or authz_payload.get("subject.id") or ""),
    }


def _normalize_business_logic(logic_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(logic_payload, dict):
        return {"entity.id": "", "entity.owner_id": ""}
    return {
        "entity.id": str(logic_payload.get("entity_id") or logic_payload.get("entity.id") or ""),
        "entity.owner_id": str(logic_payload.get("entity_owner_id") or logic_payload.get("entity.owner_id") or ""),
    }


def _normalize_discovery(discovery_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(discovery_payload, dict):
        return {"response_contains_schema": False, "openapi_security_schemes_present": False}
    return {
        "response_contains_schema": bool(discovery_payload.get("schema_found", False)),
        "openapi_security_schemes_present": bool(discovery_payload.get("security_schemes_present", False)),
    }


def _normalize_tls(tls_payload: Dict[str, Any] | None) -> Dict[str, Any]:
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


def _normalize_handler_output(handler: str, output: Dict[str, Any] | None) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
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


def normalize_execution_output(handler: str, output: Dict[str, Any] | None) -> Dict[str, Any]:
    normalized = {
        "target_reachable": True,
        "prerequisites_missing": bool((output or {}).get("prerequisites_missing", False)),
        "handler_signal": str((output or {}).get("finding") or (output or {}).get("status") or ""),
    }
    if (output or {}).get("status") == "error":
        normalized["prerequisites_missing"] = True
    normalized.update(_normalize_handler_output(handler, output))
    return normalized


def load_signal_catalog() -> Dict[str, SignalDefinition]:
    return _load_signal_catalog()


def load_canonical_mapping() -> Dict[str, Dict[str, Any]]:
    if not MAPPING_PATH.exists():
        return {}
    data = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))
    return {str(item.get("runbook_id")): item for item in (data.get("mappings") or []) if item.get("runbook_id")}


__all__ = [
    "EvaluationResult",
    "SignalDefinition",
    "SignalError",
    "load_canonical_mapping",
    "load_signal_catalog",
    "normalize_execution_output",
    "evaluate_signals",
]
