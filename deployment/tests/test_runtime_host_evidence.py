from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deployment" / "runtime-promotion" / "runtime_host_evidence.py"
DESCRIPTOR_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "runtime-host-evidence-descriptor.example.yaml"
)
TB1_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "tb1-authorization-deployment-descriptor.example.yaml"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


host_evidence = _load("runtime_host_evidence_test", MODULE_PATH)


def _descriptor() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(DESCRIPTOR_PATH.read_text(encoding="utf-8")))


def _declared_trust_store() -> dict[str, Any]:
    tb1 = yaml.safe_load(TB1_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(tb1["trust_store"]["document"])


class FakeObserver:
    def __init__(self) -> None:
        self.users = {
            "hexor-gateway": {
                "user": "hexor-gateway",
                "uid": 4100,
                "gid": 4100,
                "shell": "/usr/sbin/nologin",
            },
            "hexor-runner": {
                "user": "hexor-runner",
                "uid": 4101,
                "gid": 4101,
                "shell": "/usr/sbin/nologin",
            },
        }
        self.groups = {
            "hexor-dispatch": {
                "group": "hexor-dispatch",
                "gid": 4110,
                "members": ["hexor-gateway", "hexor-runner"],
            }
        }
        self.paths = {
            "/run/hexor": host_evidence.PathObservation(
                exists=True,
                kind="directory",
                uid=4101,
                gid=4110,
                mode="0750",
                symlink=False,
            ),
            "/run/hexor/runner-dispatch.sock": host_evidence.PathObservation(
                exists=True,
                kind="socket",
                uid=4101,
                gid=4110,
                mode="0660",
                symlink=False,
            ),
            "/etc/hexor/runner/authorization-trust-store.json": host_evidence.PathObservation(
                exists=True,
                kind="file",
                uid=0,
                gid=4101,
                mode="0640",
                symlink=False,
            ),
        }
        self.documents = {
            "/etc/hexor/runner/authorization-trust-store.json": _declared_trust_store()
        }

    def user(self, name: str):
        return copy.deepcopy(self.users.get(name))

    def group(self, name: str):
        return copy.deepcopy(self.groups.get(name))

    def path(self, path: str):
        return copy.deepcopy(
            self.paths.get(path, host_evidence.PathObservation(exists=False))
        )

    def json_document(self, path: str):
        document = self.documents.get(path)
        if document is None:
            raise host_evidence.HostEvidenceError(
                "TRUST_STORE_UNREADABLE", "installed trust store cannot be read"
            )
        return copy.deepcopy(document)


def test_declared_host_state_passes_but_never_allows_promotion() -> None:
    result = host_evidence.collect_host_evidence(
        _descriptor(), observer=FakeObserver()
    )
    assert result.host_checks_passed is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert result.findings == ()
    assert "USER_NAMESPACE_MAPPING_NOT_OBSERVED" in result.remaining_evidence
    assert "SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED" in result.remaining_evidence
    assert "UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN" in result.remaining_evidence
    assert "LIVE_AUDIT_SINK_NOT_OBSERVED" in result.remaining_evidence
    assert "LIVE_RUNNER_EFFECT_NOT_RUN" in result.remaining_evidence


def test_observations_are_sanitized_and_trust_store_is_hash_only() -> None:
    result = host_evidence.collect_host_evidence(
        _descriptor(), observer=FakeObserver()
    )
    report = result.as_dict()
    trust = report["observations"]["trust_store"]
    assert trust["document_matches_declaration"] is True
    assert len(trust["document_sha256"]) == 64
    assert trust["document_sha256"] == trust["declared_sha256"]
    serialized = json.dumps(report, sort_keys=True)
    assert "public_key" not in serialized
    assert "tb1-authorization-example-ed25519" not in serialized


def test_missing_or_mismatched_service_account_fails_closed() -> None:
    observer = FakeObserver()
    del observer.users["hexor-gateway"]
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any("gateway account" in finding and "absent" in finding for finding in result.findings)

    observer = FakeObserver()
    observer.users["hexor-runner"]["uid"] = 9999
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any("runner account uid mismatch" in finding for finding in result.findings)


def test_dispatch_group_identity_and_membership_are_observed() -> None:
    observer = FakeObserver()
    observer.groups["hexor-dispatch"]["members"] = ["hexor-gateway"]
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any("missing expected members" in finding for finding in result.findings)

    observer = FakeObserver()
    observer.groups["hexor-dispatch"]["gid"] = 4999
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert any("dispatch group gid mismatch" in finding for finding in result.findings)


@pytest.mark.parametrize(
    "path,mutation,expected",
    [
        (
            "/run/hexor/runner-dispatch.sock",
            host_evidence.PathObservation(exists=False),
            "Runner dispatch socket is absent",
        ),
        (
            "/run/hexor/runner-dispatch.sock",
            host_evidence.PathObservation(
                exists=True, kind="socket", uid=4101, gid=4110, mode="0666", symlink=False
            ),
            "Runner dispatch socket mode mismatch",
        ),
        (
            "/run/hexor",
            host_evidence.PathObservation(
                exists=True, kind="directory", uid=4101, gid=4110, mode="0750", symlink=True
            ),
            "socket directory must not be a symlink",
        ),
        (
            "/etc/hexor/runner/authorization-trust-store.json",
            host_evidence.PathObservation(
                exists=True, kind="file", uid=4101, gid=4101, mode="0640", symlink=False
            ),
            "Runner authorization trust store uid mismatch",
        ),
    ],
)
def test_socket_directory_and_trust_store_stat_mismatches_fail_closed(
    path: str, mutation, expected: str
) -> None:  # noqa: ANN001
    observer = FakeObserver()
    observer.paths[path] = mutation
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any(expected in finding for finding in result.findings)


def test_installed_trust_store_must_exactly_match_approved_public_document() -> None:
    observer = FakeObserver()
    observer.documents[
        "/etc/hexor/runner/authorization-trust-store.json"
    ]["keys"][0]["state"] = "revoked"
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any("does not match approved declaration" in finding for finding in result.findings)
    trust = result.observations["trust_store"]
    assert trust["document_matches_declaration"] is False


def test_unreadable_trust_store_is_a_finding_not_a_secret_leak() -> None:
    observer = FakeObserver()
    observer.documents.clear()
    result = host_evidence.collect_host_evidence(_descriptor(), observer=observer)
    assert result.host_checks_passed is False
    assert any("cannot be read" in finding for finding in result.findings)


def test_descriptor_remains_non_operational_and_path_safe() -> None:
    descriptor = _descriptor()
    descriptor["runtime_status"] = "READY"
    with pytest.raises(host_evidence.HostEvidenceError) as exc:
        host_evidence.collect_host_evidence(descriptor, observer=FakeObserver())
    assert exc.value.code == "DESCRIPTOR_INVALID"

    descriptor = _descriptor()
    descriptor["identity_descriptor"] = "deployment/runtime-promotion/../../outside.yaml"
    with pytest.raises(host_evidence.HostEvidenceError):
        host_evidence.collect_host_evidence(descriptor, observer=FakeObserver())


def test_trust_store_owner_must_be_independent_of_execution_identities() -> None:
    descriptor = _descriptor()
    descriptor["trust_store_expectation"]["owner_uid"] = 4101
    observer = FakeObserver()
    observer.paths[
        "/etc/hexor/runner/authorization-trust-store.json"
    ] = host_evidence.PathObservation(
        exists=True, kind="file", uid=4101, gid=4101, mode="0640", symlink=False
    )
    result = host_evidence.collect_host_evidence(descriptor, observer=observer)
    assert result.host_checks_passed is False
    assert any("owner must be independent" in finding for finding in result.findings)


def test_collector_source_has_no_mutating_or_external_execution_paths() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "requests", "urllib", "shutil"}
    for forbidden in (
        "os.chmod",
        "os.chown",
        "os.mkdir",
        "os.makedirs",
        "os.remove",
        "os.unlink",
        "os.rename",
        "write_text(",
        "write_bytes(",
        "execute_command",
        "execute_runbook",
        "docker",
    ):
        assert forbidden not in source
