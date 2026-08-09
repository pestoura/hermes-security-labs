"""Conformance tests for the Lane H backend abstraction.

These tests are hermetic: they never start, stop or touch a runtime. They pin the
contract (types, operations), the registry invariants, the fail-closed resolver and
the honesty rule that only Docker Compose is implemented.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
MODULE_PATH = PLATFORM / "scripts" / "lab_backends.py"
REGISTRY_PATH = PLATFORM / "backends" / "backend-registry.yaml"
ENVIRONMENTS = PLATFORM / "environments"

spec = importlib.util.spec_from_file_location("lab_backends", MODULE_PATH)
assert spec and spec.loader
lab_backends = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lab_backends
spec.loader.exec_module(lab_backends)


@pytest.fixture(scope="module")
def registry():
    return lab_backends.load_registry()


@pytest.fixture()
def raw_registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "backend-registry.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #


def test_backend_types_are_exactly_the_five_declared() -> None:
    assert lab_backends.BACKEND_TYPES == ("DOCKER", "VM", "KUBERNETES", "CLOUD", "REMOTE_ISOLATED")


def test_operation_vocabulary_is_bounded() -> None:
    assert lab_backends.OPERATIONS == ("provision", "status", "reset", "destroy")
    assert lab_backends.DESTRUCTIVE_OPERATIONS == {"reset", "destroy"}


def test_registry_covers_every_backend_type(registry) -> None:
    assert set(registry.specs) == set(lab_backends.BACKEND_TYPES)


def test_only_docker_is_supported_and_ready(registry) -> None:
    supported = {name for name, s in registry.specs.items() if s.is_supported}
    ready = {name for name, s in registry.specs.items() if s.is_ready}
    assert supported == {"DOCKER"}
    assert ready == {"DOCKER"}


def test_unimplemented_backends_declare_missing_capabilities(registry) -> None:
    for name in ("VM", "KUBERNETES", "CLOUD", "REMOTE_ISOLATED"):
        spec_ = registry.specs[name]
        assert spec_.support_state == "DEFINED"
        assert spec_.readiness == "NOT_READY"
        assert spec_.adapter is None
        assert spec_.missing_capabilities, f"{name} must say what is missing"
        assert set(spec_.missing_capabilities) <= set(spec_.required_capabilities)
        assert not spec_.operations, f"{name} must not map operations"


def test_docker_maps_every_operation_to_an_allowlisted_action(registry) -> None:
    docker = registry.specs["DOCKER"]
    assert set(docker.operations) == set(lab_backends.OPERATIONS)
    assert set(docker.operations.values()) <= lab_backends.DOCKER_ACTION_ALLOWLIST
    assert docker.operations["provision"] == "start"
    assert docker.operations["destroy"] == "destroy"


def test_registry_source_has_no_free_form_command_field(raw_registry: dict) -> None:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    for forbidden in ("shell:", "command:", "exec:"):
        assert forbidden not in text, f"{forbidden} must not appear in the backend registry"


# --------------------------------------------------------------------------- #
# Registry validation is fail-closed
# --------------------------------------------------------------------------- #


def test_unknown_schema_version_is_rejected(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["schema_version"] = 99
    with pytest.raises(lab_backends.BackendError, match="BACKEND_REGISTRY_INVALID"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_missing_backend_type_is_rejected(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"].pop("CLOUD")
    with pytest.raises(lab_backends.BackendError, match="must cover exactly"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_ready_without_supported_is_rejected(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"]["VM"]["readiness"] = "READY"
    with pytest.raises(lab_backends.BackendError, match="READY"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_not_ready_without_missing_capabilities_is_rejected(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"]["VM"]["missing_capabilities"] = []
    with pytest.raises(lab_backends.BackendError, match="declares no missing capability"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_defined_backend_may_not_map_operations(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"]["CLOUD"]["operations"] = {"provision": "start"}
    with pytest.raises(lab_backends.BackendError, match="must not map operations"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_defined_backend_may_not_name_an_adapter(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"]["KUBERNETES"]["adapter"] = "docker_compose"
    with pytest.raises(lab_backends.BackendError, match="names adapter"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_duplicate_alias_is_rejected(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["backends"]["CLOUD"]["manifest_aliases"] = ["docker-compose"]
    with pytest.raises(lab_backends.BackendError, match="claimed by both"):
        lab_backends.load_registry(_write(tmp_path, bad))


def test_operation_vocabulary_cannot_be_widened_by_the_registry(tmp_path: Path, raw_registry: dict) -> None:
    bad = copy.deepcopy(raw_registry)
    bad["operations"] = [*lab_backends.OPERATIONS, "exec"]
    with pytest.raises(lab_backends.BackendError, match="operations must be exactly"):
        lab_backends.load_registry(_write(tmp_path, bad))


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #


def _manifest(**overrides):
    data = {"id": "sample", "execution_class": "executable", "backend": "docker-compose"}
    data.update(overrides)
    return data


def test_resolver_maps_docker_compose_alias(registry) -> None:
    binding = lab_backends.resolve_backend(_manifest(), registry=registry)
    assert binding.spec.backend_type == "DOCKER"
    assert isinstance(binding.adapter, lab_backends.DockerComposeBackendAdapter)


def test_resolver_maps_kind_to_kubernetes_but_stays_unavailable(registry) -> None:
    binding = lab_backends.resolve_backend(_manifest(backend="kind"), registry=registry)
    assert binding.spec.backend_type == "KUBERNETES"
    assert isinstance(binding.adapter, lab_backends.UnavailableBackendAdapter)


def test_resolver_fails_closed_on_unknown_backend(registry) -> None:
    with pytest.raises(lab_backends.BackendError, match="BACKEND_UNKNOWN"):
        lab_backends.resolve_backend(_manifest(backend="podman-magic"), registry=registry)


def test_resolver_fails_closed_on_missing_backend(registry) -> None:
    manifest = _manifest()
    manifest.pop("backend")
    with pytest.raises(lab_backends.BackendError, match="BACKEND_FIELD_MISSING"):
        lab_backends.resolve_backend(manifest, registry=registry)


def test_resolver_fails_closed_on_empty_backend(registry) -> None:
    with pytest.raises(lab_backends.BackendError, match="BACKEND_FIELD_MISSING"):
        lab_backends.resolve_backend(_manifest(backend="   "), registry=registry)


def test_catalog_only_manifest_has_no_backend_binding(registry) -> None:
    with pytest.raises(lab_backends.BackendError, match="not executable"):
        lab_backends.resolve_backend(_manifest(execution_class="catalog"), registry=registry)


def test_alias_matching_is_case_insensitive(registry) -> None:
    binding = lab_backends.resolve_backend(_manifest(backend="Docker-Compose"), registry=registry)
    assert binding.spec.backend_type == "DOCKER"


# --------------------------------------------------------------------------- #
# Adapters / plans
# --------------------------------------------------------------------------- #


class _FakeResolution:
    def __init__(self, argv):
        self.argv = argv


def _fake_resolver(env_id: str, action: str):
    if action not in {"start", "status", "reset", "destroy"}:
        raise RuntimeError(f"unsupported action {action}")
    return _FakeResolution(("bash", f"/labs/{env_id}/scripts/{action}.sh"))


def test_docker_plan_is_descriptive_and_bounded(registry) -> None:
    adapter = lab_backends.DockerComposeBackendAdapter(registry.specs["DOCKER"], resolver=_fake_resolver)
    plan = adapter.plan("dvwa", "provision")
    assert plan.action == "start"
    assert plan.destructive is False
    assert plan.executable is True
    assert plan.argv == ("bash", "/labs/dvwa/scripts/start.sh")


def test_docker_plan_marks_destructive_operations(registry) -> None:
    adapter = lab_backends.DockerComposeBackendAdapter(registry.specs["DOCKER"], resolver=_fake_resolver)
    for operation in ("reset", "destroy"):
        assert adapter.plan("dvwa", operation).destructive is True


def test_docker_plan_degrades_to_non_executable_without_script(registry) -> None:
    def broken(env_id: str, action: str):
        raise RuntimeError("no shipped script")

    adapter = lab_backends.DockerComposeBackendAdapter(registry.specs["DOCKER"], resolver=broken)
    plan = adapter.plan("ghost", "status")
    assert plan.executable is False
    assert plan.argv == ()
    assert plan.notes


def test_unknown_operation_fails_closed(registry) -> None:
    adapter = lab_backends.DockerComposeBackendAdapter(registry.specs["DOCKER"], resolver=_fake_resolver)
    with pytest.raises(lab_backends.BackendError, match="OPERATION_UNKNOWN"):
        adapter.plan("dvwa", "exec")


def test_unavailable_adapter_refuses_every_operation(registry) -> None:
    for name in ("VM", "KUBERNETES", "CLOUD", "REMOTE_ISOLATED"):
        adapter = lab_backends.adapter_for(registry.specs[name])
        assert isinstance(adapter, lab_backends.UnavailableBackendAdapter)
        for operation in lab_backends.OPERATIONS:
            with pytest.raises(lab_backends.BackendError, match="BACKEND_NOT_SUPPORTED"):
                adapter.plan("whatever", operation)


def test_unavailable_adapter_reports_missing_capabilities(registry) -> None:
    adapter = lab_backends.adapter_for(registry.specs["CLOUD"])
    report = adapter.capability_report()
    assert report["readiness"] == "NOT_READY"
    assert "scoped_cloud_credential" in report["missing_capabilities"]


def test_adapter_interface_has_no_execution_entrypoint() -> None:
    forbidden = {"run", "execute", "provision", "destroy", "apply"}
    assert forbidden.isdisjoint(dir(lab_backends.BackendAdapter))


def test_module_never_spawns_a_shell() -> None:
    """Prose may mention shells; the executable AST must contain none."""
    import ast

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
    }
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "subprocess" not in imported
    assert "os" not in imported
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "shell":
            raise AssertionError("no call may pass a shell= keyword")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec", "system"}


# --------------------------------------------------------------------------- #
# Repository reality: bindings for the shipped manifests
# --------------------------------------------------------------------------- #


def test_every_executable_manifest_binds_to_a_known_backend(registry) -> None:
    rows = lab_backends.backend_matrix(registry)
    assert rows, "expected at least one executable manifest"
    for row in rows:
        assert row["resolution"] == "RESOLVED", row


def test_kind_environment_binds_to_kubernetes_not_ready(registry) -> None:
    rows = {row["env_id"]: row for row in lab_backends.backend_matrix(registry)}
    kind_rows = [r for r in rows.values() if r["declared_backend"] == "kind"]
    assert kind_rows, "expected the synthetic kind environment"
    for row in kind_rows:
        assert row["backend_type"] == "KUBERNETES"
        assert row["readiness"] == "NOT_READY"


def test_docker_compose_environments_are_ready(registry) -> None:
    rows = [r for r in lab_backends.backend_matrix(registry) if r["declared_backend"] == "docker-compose"]
    assert rows
    for row in rows:
        assert row["backend_type"] == "DOCKER"
        assert row["readiness"] == "READY"


def test_manifest_backend_values_are_all_declared_in_the_registry(registry) -> None:
    for path in sorted(ENVIRONMENTS.rglob("manifest.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("execution_class") != "executable":
            continue
        registry.resolve_alias(str(data.get("backend", "")))


def test_real_dispatcher_seam_resolves_a_shipped_script(registry) -> None:
    """The non-invasive seam onto lab_lifecycle.resolve works against real content."""
    binding = lab_backends.resolve_backend(
        yaml.safe_load((ENVIRONMENTS / "web-api" / "dvwa" / "manifest.yaml").read_text(encoding="utf-8")),
        registry=registry,
    )
    plan = binding.adapter.plan("dvwa", "provision")
    assert plan.executable is True
    assert plan.argv[0] == "bash"
    assert plan.argv[-1].endswith("/environments/web-api/dvwa/scripts/start.sh")

