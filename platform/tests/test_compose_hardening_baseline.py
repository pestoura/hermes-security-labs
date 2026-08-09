"""Transversal container-hardening invariants for every committed Compose file.

This test codifies the repository-wide isolation baseline so that a new (or
edited) laboratory cannot silently weaken it. It is intentionally static: it
parses the committed Compose files and never starts a container.

Two classes of rule are enforced:

* Universal invariants - no exceptions are accepted. A violation is a
  regression regardless of which laboratory introduced it.
* Baseline invariants - enforced with an explicit, reviewed exception list.
  Exceptions are recorded here so that removing one is a visible, reviewable
  change and adding a new one requires editing this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_PARTS = {".git", ".runtime", "node_modules", "__pycache__"}

# Host bind mounts are forbidden except for the Kali evidence/cache directories,
# which are project-relative and hold sanitized results only.
ALLOWED_BIND_MOUNTS = {
    "./data/results:/data/results",
    "./data/cache:/data/cache",
}

# Services that legitimately keep a writable root filesystem: upstream
# vulnerable-lab images that write to their own application directories and
# cannot run with a read-only rootfs without a custom image.
WRITABLE_ROOTFS_EXCEPTIONS = {
    "compose.yaml::kali-maintenance",
    "kali-mcp/compose.yaml::kali-maintenance",
    "platform/environments/devsecops/wrongsecrets/compose.yaml::wrongsecrets",
    "platform/environments/web-api/crapi/compose.yaml::crapi-identity",
    "platform/environments/web-api/crapi/compose.yaml::crapi-community",
    "platform/environments/web-api/crapi/compose.yaml::crapi-workshop",
    "platform/environments/web-api/crapi/compose.yaml::crapi-web",
    "platform/environments/web-api/crapi/compose.yaml::gateway",
    "platform/environments/web-api/crapi/compose.yaml::mailhog",
    "platform/environments/web-api/crapi/compose.yaml::postgresdb",
    "platform/environments/web-api/crapi/compose.yaml::mongodb",
    "platform/environments/web-api/dvapi/compose.yaml::dvapi",
    "platform/environments/web-api/dvapi/compose.yaml::mongodb",
    "platform/environments/web-api/dvwa/compose.yaml::dvwa",
    "platform/environments/web-api/dvwa/compose.yaml::db",
    "platform/environments/web-api/graphql-vulnerable-lab/compose.yaml::graphql-vulnerable-lab",
    "platform/environments/web-api/juice-shop/compose.yaml::juice-shop",
    "platform/environments/web-api/nodegoat/compose.yaml::nodegoat",
    "platform/environments/web-api/nodegoat/compose.yaml::mongo",
    "platform/environments/web-api/pygoat/compose.yaml::pygoat",
    "platform/environments/web-api/vampi/compose.yaml::vampi",
    "platform/environments/web-api/webgoat/compose.yaml::webgoat",
}

# Services that drop only NET_RAW instead of ALL: upstream images whose
# entrypoints still require the default capability set to bind and chown.
PARTIAL_CAP_DROP_EXCEPTIONS = {
    "platform/environments/web-api/crapi/compose.yaml::crapi-identity",
    "platform/environments/web-api/crapi/compose.yaml::crapi-community",
    "platform/environments/web-api/crapi/compose.yaml::crapi-workshop",
    "platform/environments/web-api/crapi/compose.yaml::crapi-web",
    "platform/environments/web-api/crapi/compose.yaml::gateway",
    "platform/environments/web-api/crapi/compose.yaml::mailhog",
    "platform/environments/web-api/crapi/compose.yaml::postgresdb",
    "platform/environments/web-api/crapi/compose.yaml::mongodb",
    "platform/environments/web-api/dvapi/compose.yaml::dvapi",
    "platform/environments/web-api/dvapi/compose.yaml::mongodb",
    "platform/environments/web-api/dvwa/compose.yaml::dvwa",
    "platform/environments/web-api/dvwa/compose.yaml::db",
    "platform/environments/web-api/graphql-vulnerable-lab/compose.yaml::graphql-vulnerable-lab",
    "platform/environments/web-api/nodegoat/compose.yaml::nodegoat",
    "platform/environments/web-api/nodegoat/compose.yaml::mongo",
    "platform/environments/web-api/pygoat/compose.yaml::pygoat",
    "platform/environments/web-api/vampi/compose.yaml::vampi",
}

# Images that are still tag-pinned instead of digest-pinned. Tracked as a
# supply-chain gap; the set must only ever shrink. It is now empty: every
# committed Compose service references an immutable `@sha256:` digest.
TAG_PINNED_IMAGE_EXCEPTIONS: set[str] = set()


def _compose_files() -> list[Path]:
    files = [
        path
        for path in ROOT.rglob("compose*.y*ml")
        if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
    ]
    assert files, "no Compose files discovered"
    return sorted(files)


def _services() -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path in _compose_files():
        rel = path.relative_to(ROOT).as_posix()
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, service in (document.get("services") or {}).items():
            yield rel, name, service or {}


def _limits(service: dict[str, Any]) -> dict[str, Any]:
    return ((service.get("deploy") or {}).get("resources") or {}).get("limits") or {}


def _ref(rel: str, name: str) -> str:
    return f"{rel}::{name}"


def test_no_privileged_or_host_namespace_escape() -> None:
    for rel, name, service in _services():
        ref = _ref(rel, name)
        assert service.get("privileged") is not True, f"{ref} runs privileged"
        assert "cap_add" not in service, f"{ref} adds capabilities"
        assert service.get("network_mode") is None, f"{ref} overrides network mode"
        assert service.get("pid") is None, f"{ref} shares a PID namespace"
        assert service.get("ipc") is None, f"{ref} shares an IPC namespace"
        assert service.get("userns_mode") is None, f"{ref} overrides the user namespace"


def test_docker_socket_is_never_mounted() -> None:
    for path in _compose_files():
        text = path.read_text(encoding="utf-8")
        assert "docker.sock" not in text, f"{path} exposes the Docker socket"


def test_only_allowlisted_host_bind_mounts_exist() -> None:
    for rel, name, service in _services():
        document = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8")) or {}
        named = set(document.get("volumes") or {})
        for volume in service.get("volumes") or []:
            if not isinstance(volume, str):
                source = (volume or {}).get("source")
                assert (volume or {}).get("type") == "volume", (
                    f"{_ref(rel, name)} uses a long-form non-volume mount: {volume}"
                )
                assert source in named, f"{_ref(rel, name)} mounts unknown volume {source}"
                continue
            source = volume.split(":", 1)[0]
            if source in named:
                continue
            assert volume in ALLOWED_BIND_MOUNTS, (
                f"{_ref(rel, name)} declares an unapproved host bind mount: {volume}"
            )


def test_published_ports_are_loopback_only() -> None:
    for rel, name, service in _services():
        for port in service.get("ports") or []:
            assert isinstance(port, str), f"{_ref(rel, name)} uses a non-string port mapping"
            assert port.startswith("127.0.0.1:"), (
                f"{_ref(rel, name)} publishes {port} outside loopback"
            )


def test_every_service_declares_cpu_memory_and_pid_limits() -> None:
    for rel, name, service in _services():
        limits = _limits(service)
        missing = [key for key in ("cpus", "memory", "pids") if key not in limits]
        assert not missing, f"{_ref(rel, name)} is missing resource limits: {missing}"


def test_no_new_privileges_is_always_set() -> None:
    for rel, name, service in _services():
        options = service.get("security_opt") or []
        assert any("no-new-privileges" in str(option) for option in options), (
            f"{_ref(rel, name)} does not set no-new-privileges"
        )


def test_capabilities_are_dropped_with_reviewed_exceptions() -> None:
    for rel, name, service in _services():
        ref = _ref(rel, name)
        dropped = {str(item).upper() for item in service.get("cap_drop") or []}
        assert dropped, f"{ref} does not drop capabilities"
        if "ALL" in dropped:
            continue
        assert ref in PARTIAL_CAP_DROP_EXCEPTIONS, f"{ref} drops only {sorted(dropped)}"


def test_read_only_rootfs_with_reviewed_exceptions() -> None:
    for rel, name, service in _services():
        ref = _ref(rel, name)
        if service.get("read_only") is True:
            continue
        assert ref in WRITABLE_ROOTFS_EXCEPTIONS, f"{ref} unexpectedly keeps a writable rootfs"


def test_images_are_digest_pinned_with_reviewed_exceptions() -> None:
    for rel, name, service in _services():
        image = service.get("image")
        if image is None:
            continue
        ref = _ref(rel, name)
        if "@sha256:" in image:
            continue
        assert ref in TAG_PINNED_IMAGE_EXCEPTIONS, f"{ref} uses a mutable image reference: {image}"


def test_no_compose_service_uses_a_mutable_image_reference() -> None:
    """The digest-pin exception set is closed: nothing may reopen it silently."""
    assert TAG_PINNED_IMAGE_EXCEPTIONS == set(), (
        "the tag-pinned exception set must stay empty: "
        f"{sorted(TAG_PINNED_IMAGE_EXCEPTIONS)}"
    )
    for rel, name, service in _services():
        image = service.get("image")
        if image is None:
            continue
        assert "@sha256:" in image, (
            f"{_ref(rel, name)} uses a mutable image reference: {image}"
        )


def test_exception_lists_contain_no_stale_entries() -> None:
    known = {_ref(rel, name) for rel, name, _ in _services()}
    for label, entries in (
        ("writable rootfs", WRITABLE_ROOTFS_EXCEPTIONS),
        ("partial cap_drop", PARTIAL_CAP_DROP_EXCEPTIONS),
        ("tag-pinned image", TAG_PINNED_IMAGE_EXCEPTIONS),
    ):
        stale = sorted(entries - known)
        assert not stale, f"stale {label} exceptions: {stale}"
