#!/usr/bin/env python3
"""Read-only maturity audit for Hermes Security Labs environments.

The audit answers one question per environment: *is this lab reproducible and
onboardable without tribal knowledge?* It never starts, stops or otherwise
touches a runtime; it only reads manifests, compose files and lifecycle
scripts that live in the repository.

Environments are split into two populations:

``runtime-managed``
    Directory manifests (``manifest.yaml``) that ship a ``compose.yaml``. These
    are audited against the reproducibility contract below.

``catalog-only``
    Flat YAML manifests with no runtime assets in the repository. They are
    catalogued but carry no lifecycle guarantees, so they are reported as
    ``CATALOG-ONLY`` instead of being scored.

Reproducibility contract for runtime-managed labs:

* lifecycle: ``start.sh``, ``stop.sh``, ``reset.sh``, ``destroy.sh``,
  ``status.sh``, ``smoke.sh`` are present (missing start/stop/destroy is fatal).
* kali connectivity: ``connect-kali.sh`` and ``disconnect-kali.sh`` are present.
* determinism: every service image is pinned by ``@sha256:`` digest.
* observability: every image-backed service declares a ``healthcheck``.
* exposure: every published port binds ``127.0.0.1`` (non-loopback is fatal)
  and uses an overridable ``${VAR:-default}`` host port.
* isolation: multi-service labs declare at least one ``internal: true`` network
  for their backing services.

Verdicts: ``PASS`` (no findings), ``DEGRADED`` (only warnings),
``FAIL`` (at least one fatal finding).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency is declared in CI
    raise SystemExit("PyYAML is required to use platform/scripts/lab_audit.py") from exc

PLATFORM_DIR = Path(__file__).resolve().parents[1]
ENVIRONMENTS_DIR = PLATFORM_DIR / "environments"
BASELINE_PATH = PLATFORM_DIR / "lab-audit-baseline.yaml"

CRITICAL_SCRIPTS = ("start.sh", "stop.sh", "destroy.sh")
EXPECTED_SCRIPTS = CRITICAL_SCRIPTS + ("reset.sh", "status.sh", "smoke.sh")
KALI_SCRIPTS = ("connect-kali.sh", "disconnect-kali.sh")

PARAMETERISED_PORT = re.compile(r"\$\{[A-Z0-9_]+:-[^}]+\}")

VERDICT_PASS = "PASS"
VERDICT_DEGRADED = "DEGRADED"
VERDICT_FAIL = "FAIL"
VERDICT_CATALOG_ONLY = "CATALOG-ONLY"


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _published_ports(service: dict[str, Any]) -> list[str]:
    ports = service.get("ports") or []
    published: list[str] = []
    for entry in ports:
        if isinstance(entry, dict):
            host_ip = str(entry.get("host_ip", ""))
            published_port = str(entry.get("published", ""))
            published.append(f"{host_ip}:{published_port}" if host_ip else published_port)
        else:
            published.append(str(entry))
    return published


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PLATFORM_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def audit_environment(manifest_path: Path) -> dict[str, Any]:
    """Audit a single manifest. Never raises for content problems."""

    data = _load_yaml(manifest_path)
    if not isinstance(data, dict):
        data = {}
    env_dir = manifest_path.parent
    compose_path = env_dir / "compose.yaml"
    env_id = str(data.get("id", manifest_path.stem))

    result: dict[str, Any] = {
        "id": env_id,
        "status": str(data.get("status", "")),
        "runtime": str(data.get("runtime", "")),
        "manifest": _display_path(manifest_path),
        "population": "catalog-only",
        "verdict": VERDICT_CATALOG_ONLY,
        "fatal": [],
        "warnings": [],
    }

    if manifest_path.name != "manifest.yaml" or not compose_path.is_file():
        return result

    result["population"] = "runtime-managed"
    fatal: list[str] = []
    warnings: list[str] = []

    scripts = {path.name for path in (env_dir / "scripts").glob("*.sh")}
    for name in EXPECTED_SCRIPTS:
        if name in scripts:
            continue
        (fatal if name in CRITICAL_SCRIPTS else warnings).append(f"missing-script:{name}")
    for name in KALI_SCRIPTS:
        if name not in scripts:
            warnings.append(f"missing-kali-script:{name}")

    try:
        compose = _load_yaml(compose_path)
    except yaml.YAMLError as exc:
        fatal.append(f"unparsable-compose:{exc.__class__.__name__}")
        compose = None

    if isinstance(compose, dict):
        services = compose.get("services") or {}
        image_services = {
            name: service
            for name, service in services.items()
            if isinstance(service, dict) and service.get("image")
        }
        for name, service in sorted(image_services.items()):
            image = str(service["image"])
            if "@sha256:" not in image:
                warnings.append(f"unpinned-image:{name}")
            if "healthcheck" not in service:
                warnings.append(f"missing-healthcheck:{name}")
            for published in _published_ports(service):
                if not published.startswith("127.0.0.1:"):
                    fatal.append(f"non-loopback-port:{name}:{published}")
                elif not PARAMETERISED_PORT.search(published):
                    warnings.append(f"fixed-host-port:{name}:{published}")

        networks = compose.get("networks") or {}
        has_internal = any(
            isinstance(spec, dict) and spec.get("internal") is True
            for spec in networks.values()
        )
        if len(image_services) > 1 and not has_internal:
            warnings.append("no-internal-network")

    if fatal:
        result["verdict"] = VERDICT_FAIL
    elif warnings:
        result["verdict"] = VERDICT_DEGRADED
    else:
        result["verdict"] = VERDICT_PASS
    result["fatal"] = sorted(fatal)
    result["warnings"] = sorted(warnings)
    return result


def audit_catalog() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(ENVIRONMENTS_DIR.rglob("*.yaml")):
        if path.name in {"compose.yaml", "compose-effective.yaml"}:
            continue
        try:
            data = _load_yaml(path)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict) or "id" not in data or "runtime" not in data:
            continue
        results.append(audit_environment(path))
    return sorted(results, key=lambda item: item["id"])


def load_baseline() -> dict[str, str]:
    if not BASELINE_PATH.is_file():
        return {}
    data = _load_yaml(BASELINE_PATH)
    if not isinstance(data, dict):
        return {}
    verdicts = data.get("verdicts") or {}
    return {str(key): str(value) for key, value in verdicts.items()}


def _print_table(results: list[dict[str, Any]]) -> None:
    print("verdict\tid\tstatus\tpopulation\tfindings")
    for item in results:
        findings = ",".join(item["fatal"] + item["warnings"]) or "-"
        print(
            f"{item['verdict']}\t{item['id']}\t{item['status']}\t"
            f"{item['population']}\t{findings}"
        )


def cmd_audit(args: argparse.Namespace) -> int:
    results = audit_catalog()
    if args.runtime_managed:
        results = [item for item in results if item["population"] == "runtime-managed"]
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        _print_table(results)
    if args.strict and any(item["verdict"] == VERDICT_FAIL for item in results):
        return 1
    return 0


def cmd_baseline_check(_: argparse.Namespace) -> int:
    results = {item["id"]: item["verdict"] for item in audit_catalog()}
    baseline = load_baseline()
    problems: list[str] = []
    for env_id, verdict in sorted(results.items()):
        expected = baseline.get(env_id)
        if expected is None:
            problems.append(f"{env_id}: missing from {BASELINE_PATH.name}")
        elif expected != verdict:
            problems.append(f"{env_id}: baseline {expected} but audit {verdict}")
    for env_id in sorted(set(baseline) - set(results)):
        problems.append(f"{env_id}: present in baseline but absent from catalog")
    if problems:
        for problem in problems:
            print(f"FAIL\t{problem}")
        return 1
    print(f"OK\t{len(results)} environments match the audit baseline")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="audit environment maturity")
    audit.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    audit.add_argument(
        "--runtime-managed",
        action="store_true",
        help="only report environments that ship runtime assets",
    )
    audit.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any environment is FAIL",
    )
    audit.set_defaults(func=cmd_audit)

    baseline = subparsers.add_parser(
        "baseline-check", help="compare the audit against the recorded baseline"
    )
    baseline.set_defaults(func=cmd_baseline_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
