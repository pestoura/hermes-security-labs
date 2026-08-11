from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "deployment" / "runtime-promotion" / "runtime_userns_evidence.py"
DESCRIPTOR_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "runtime-userns-evidence-descriptor.example.yaml"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


userns = _load("runtime_userns_evidence_test", MODULE_PATH)


def _descriptor() -> dict[str, Any]:
    document = yaml.safe_load(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _map() -> tuple[Any, ...]:
    return (userns.NamespaceMapEntry(0, 0, 4294967295),)


class FakeObserver:
    def __init__(
        self,
        *,
        same_namespace: bool = True,
        gateway_uid_map: tuple[Any, ...] | None = None,
        gateway_gid_map: tuple[Any, ...] | None = None,
        runner_uid_map: tuple[Any, ...] | None = None,
        runner_gid_map: tuple[Any, ...] | None = None,
    ) -> None:
        common = 4026531837
        self.values = {
            42001: userns.ProcessNamespaceObservation(
                pid=42001,
                process_start_time_ticks=10001,
                user_namespace_inode=common,
                uid_map=gateway_uid_map or _map(),
                gid_map=gateway_gid_map or _map(),
            ),
            42002: userns.ProcessNamespaceObservation(
                pid=42002,
                process_start_time_ticks=10002,
                user_namespace_inode=common if same_namespace else common + 1,
                uid_map=runner_uid_map or _map(),
                gid_map=runner_gid_map or _map(),
            ),
        }
        self.calls: list[int] = []

    def observe(self, pid: int):
        self.calls.append(pid)
        return self.values[pid]


def test_example_descriptor_is_valid_but_runtime_not_run() -> None:
    descriptor = userns.load_descriptor(DESCRIPTOR_PATH)
    assert descriptor["runtime_status"] == "NOT_RUN"
    assert descriptor["processes"]["gateway"]["pid"] != descriptor["processes"]["runner"]["pid"]


def test_matching_explicit_pid_maps_pass_without_promotion() -> None:
    observer = FakeObserver()
    result = userns.collect_userns_evidence(_descriptor(), observer=observer)

    assert result.user_namespace_checks_passed is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    assert observer.calls == [42001, 42002]
    assert result.observations["user_namespace_relationship"] == "same"
    assert result.observations["gateway"]["declared_host_uid_covered"] is True
    assert result.observations["runner"]["declared_host_gid_covered"] is True


def test_uid_map_mismatch_fails_closed() -> None:
    different = (userns.NamespaceMapEntry(0, 100000, 65536),)
    result = userns.collect_userns_evidence(
        _descriptor(), observer=FakeObserver(gateway_uid_map=different)
    )

    assert result.user_namespace_checks_passed is False
    assert result.promotion_allowed is False
    assert any("gateway uid_map differs" in item for item in result.findings)
    assert any("declared host UID" in item for item in result.findings)


def test_gid_map_mismatch_fails_closed() -> None:
    different = (userns.NamespaceMapEntry(0, 200000, 65536),)
    result = userns.collect_userns_evidence(
        _descriptor(), observer=FakeObserver(runner_gid_map=different)
    )
    assert result.user_namespace_checks_passed is False
    assert any("runner gid_map differs" in item for item in result.findings)


def test_user_namespace_relationship_is_checked() -> None:
    result = userns.collect_userns_evidence(
        _descriptor(), observer=FakeObserver(same_namespace=False)
    )
    assert result.user_namespace_checks_passed is False
    assert result.observations["user_namespace_relationship"] == "different"
    assert any("relationship differs" in item for item in result.findings)


def test_descriptor_requires_distinct_explicit_pids() -> None:
    descriptor = _descriptor()
    descriptor["processes"]["runner"]["pid"] = descriptor["processes"]["gateway"]["pid"]
    with pytest.raises(userns.UserNamespaceEvidenceError) as exc:
        userns.collect_userns_evidence(descriptor, observer=FakeObserver())
    assert exc.value.code == "DESCRIPTOR_INVALID"


def test_expected_maps_must_cover_declared_host_identity() -> None:
    descriptor = _descriptor()
    descriptor["processes"]["gateway"]["uid_map"] = [
        {"inside_start": 0, "outside_start": 100000, "length": 65536}
    ]
    observer = FakeObserver(
        gateway_uid_map=(userns.NamespaceMapEntry(0, 100000, 65536),)
    )
    result = userns.collect_userns_evidence(descriptor, observer=observer)
    assert result.user_namespace_checks_passed is False
    assert any("expected uid_map does not cover" in item for item in result.findings)


def test_overlapping_expected_map_is_refused() -> None:
    descriptor = _descriptor()
    descriptor["processes"]["gateway"]["uid_map"] = [
        {"inside_start": 0, "outside_start": 0, "length": 100},
        {"inside_start": 50, "outside_start": 1000, "length": 100},
    ]
    with pytest.raises(userns.UserNamespaceEvidenceError) as exc:
        userns.collect_userns_evidence(descriptor, observer=FakeObserver())
    assert exc.value.code == "NAMESPACE_MAP_INVALID"


def test_identity_descriptor_cannot_escape_runtime_promotion_tree() -> None:
    descriptor = _descriptor()
    descriptor["identity_descriptor"] = "deployment/runtime-promotion/../other.yaml"
    with pytest.raises(userns.UserNamespaceEvidenceError) as exc:
        userns.collect_userns_evidence(descriptor, observer=FakeObserver())
    assert exc.value.code in {"DESCRIPTOR_INVALID", "IDENTITY_DESCRIPTOR_PATH_INVALID"}


def test_proc_map_parser_is_strict_and_bounded() -> None:
    assert userns._parse_proc_map("0 100000 65536\n", "uid") == (
        userns.NamespaceMapEntry(0, 100000, 65536),
    )
    with pytest.raises(userns.UserNamespaceEvidenceError):
        userns._parse_proc_map("0 100000\n", "uid")
    with pytest.raises(userns.UserNamespaceEvidenceError):
        userns._parse_proc_map("0 100000 0\n", "uid")


def test_safe_output_excludes_process_payload_surfaces() -> None:
    result = userns.collect_userns_evidence(_descriptor(), observer=FakeObserver())
    rendered = repr(result.as_dict()).lower()
    for forbidden in ("cmdline", "environ", "authorization", "credential", "private_key"):
        assert forbidden not in rendered


def test_source_has_no_process_discovery_namespace_entry_or_mutation() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "os.listdir",
        ".iterdir(",
        ".glob(",
        "psutil",
        "subprocess",
        "socket",
        "setns",
        "unshare",
        "nsenter",
        "docker",
        "cmdline",
        "environ",
        "chmod",
        "chown",
        "kill(",
    ):
        assert forbidden not in source
    assert 'f"/proc/{pid}"' in source
    assert "promotion_allowed=False" in source
