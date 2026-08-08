from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

HERE = Path(__file__).resolve().parent


def _load_gate():
    name = "_hex0r_controlled_gateway_gate"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / "deployment_gate.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot load deployment gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


class ControlledGatewayError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _operation(registry: Mapping[str, Any], operation_id: str) -> Mapping[str, Any] | None:
    for value in registry.get("operations", []):
        if isinstance(value, Mapping) and value.get("id") == operation_id:
            return value
    return None


def evaluate_request(
    *,
    canonical_runtime: Path,
    deployed_runtime: Path,
    registry: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if not canonical_runtime.is_file() or not deployed_runtime.is_file():
        raise ControlledGatewayError("RUNTIME_FILE_REQUIRED")
    decision = GATE.evaluate_deployment_gate(
        canonical_runtime=canonical_runtime.read_bytes(),
        observed_sha256=_sha256(deployed_runtime),
        operation_registry=registry,
    )
    if decision.allowed is not True:
        return {
            "status": "REFUSED",
            "codes": list(decision.codes),
            "effect_executed": False,
            "execution_authority": "NONE",
        }

    if set(request) != {"profile", "operation_id", "parameters"}:
        return {"status": "REFUSED", "codes": ["REQUEST_SHAPE_INVALID"], "effect_executed": False, "execution_authority": "NONE"}
    profile_name = request.get("profile")
    operation_id = request.get("operation_id")
    parameters = request.get("parameters")
    profiles = registry.get("profiles", {})
    profile = profiles.get(profile_name) if isinstance(profiles, Mapping) else None
    operation = _operation(registry, str(operation_id))
    if not isinstance(profile, Mapping) or operation_id not in profile.get("operations", []):
        return {"status": "REFUSED", "codes": ["OPERATION_NOT_ALLOWED_IN_PROFILE"], "effect_executed": False, "execution_authority": "NONE"}
    if operation is None:
        return {"status": "REFUSED", "codes": ["OPERATION_UNKNOWN"], "effect_executed": False, "execution_authority": "NONE"}
    schema = operation.get("parameters_schema")
    if not isinstance(parameters, Mapping) or not isinstance(schema, Mapping):
        return {"status": "REFUSED", "codes": ["PARAMETERS_INVALID"], "effect_executed": False, "execution_authority": "NONE"}
    allowed_properties = set((schema.get("properties") or {}).keys())
    required = set(schema.get("required") or [])
    if not required.issubset(parameters) or any(key not in allowed_properties for key in parameters):
        return {"status": "REFUSED", "codes": ["PARAMETERS_SCHEMA_REFUSED"], "effect_executed": False, "execution_authority": "NONE"}

    if operation_id != "system.health.read":
        return {"status": "REFUSED", "codes": ["CONTROLLED_EFFECT_NOT_IMPLEMENTED"], "effect_executed": False, "execution_authority": "NONE"}
    return {
        "status": "PASS",
        "codes": ["TYPED_OPERATION_EXECUTED"],
        "operation_id": operation_id,
        "effect": {"health": "ok"},
        "effect_executed": True,
        "execution_authority": "CONTROLLED_CI_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled live B-01 gateway runtime candidate")
    parser.add_argument("--canonical-runtime", required=True)
    parser.add_argument("--deployed-runtime", required=True)
    parser.add_argument("--operation-registry", required=True)
    args = parser.parse_args()
    canonical = Path(args.canonical_runtime).resolve()
    deployed = Path(args.deployed_runtime).resolve()
    registry = yaml.safe_load(Path(args.operation_registry).read_text(encoding="utf-8"))
    if not isinstance(registry, Mapping):
        raise ControlledGatewayError("OPERATION_REGISTRY_REQUIRED")

    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            if not isinstance(request, Mapping):
                raise ControlledGatewayError("REQUEST_OBJECT_REQUIRED")
            response = evaluate_request(
                canonical_runtime=canonical,
                deployed_runtime=deployed,
                registry=registry,
                request=request,
            )
        except (json.JSONDecodeError, ControlledGatewayError) as exc:
            response = {"status": "REFUSED", "codes": [str(exc)], "effect_executed": False, "execution_authority": "NONE"}
        sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
