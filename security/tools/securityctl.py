#!/usr/bin/env python3
"""Unified read-only catalog and validation CLI for the security layer."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_ROOT = REPO_ROOT / "security"
PLATFORM_ROOT = REPO_ROOT / "platform"
FORBIDDEN_KEYS = {"command", "script", "shell", "argv"}
LEGACY_PLACEHOLDERS = {
    "profile-specific vulnerable signal is present",
    "profile-specific protection signal is present",
    "target unavailable or prerequisites missing",
}


@dataclass(frozen=True)
class PackSpec:
    domain: str
    root: Path
    expected: int
    schema: Path
    runbooks: Path


PACKS = {
    "api": PackSpec(
        domain="api",
        root=SECURITY_ROOT / "packs" / "api",
        expected=150,
        schema=SECURITY_ROOT / "packs" / "api" / "schemas" / "runbook.schema.json",
        runbooks=SECURITY_ROOT / "packs" / "api" / "runbooks",
    ),
    "devsecops": PackSpec(
        domain="devsecops",
        root=SECURITY_ROOT / "packs" / "devsecops",
        expected=120,
        schema=SECURITY_ROOT / "packs" / "devsecops" / "schemas" / "security-runbook.schema.json",
        runbooks=SECURITY_ROOT / "packs" / "devsecops" / "runbooks",
    ),
    "ai-mcp": PackSpec(
        domain="ai-mcp",
        root=SECURITY_ROOT / "packs" / "ai-mcp",
        expected=100,
        schema=SECURITY_ROOT / "packs" / "ai-mcp" / "schemas" / "security-runbook.schema.json",
        runbooks=SECURITY_ROOT / "packs" / "ai-mcp" / "runbooks",
    ),
}


@dataclass(frozen=True)
class Runbook:
    domain: str
    path: Path
    data: dict[str, Any]

    @property
    def runbook_id(self) -> str:
        return str(self.data.get("metadata", {}).get("id", ""))

    @property
    def category(self) -> str:
        return str(self.data.get("metadata", {}).get("category", ""))

    @property
    def status(self) -> str:
        return str(self.data.get("metadata", {}).get("status", ""))


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc


def walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield None, item
            yield from walk(item)


def load_runbooks(domain: str | None = None) -> list[Runbook]:
    domains = [domain] if domain else list(PACKS)
    entries: list[Runbook] = []
    for item_domain in domains:
        spec = PACKS[item_domain]
        for path in sorted(spec.runbooks.rglob("*.yaml")):
            data = load_yaml(path)
            if not isinstance(data, dict):
                raise ValueError(f"runbook must be an object: {path}")
            entries.append(Runbook(item_domain, path, data))
    return entries


def load_campaigns() -> dict[str, tuple[str, Path, dict[str, Any]]]:
    result: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    for domain, spec in PACKS.items():
        for path in sorted((spec.root / "campaigns").glob("*.yaml")):
            data = load_yaml(path)
            if not isinstance(data, dict):
                raise ValueError(f"campaign must be an object: {path}")
            campaign_id = str(data.get("metadata", {}).get("id", ""))
            if not campaign_id:
                raise ValueError(f"campaign without metadata.id: {path}")
            if campaign_id in result:
                raise ValueError(f"duplicate campaign id: {campaign_id}")
            result[campaign_id] = (domain, path, data)
    return result


def discover_labs() -> dict[str, Path]:
    root = PLATFORM_ROOT / "environments"
    if not root.exists():
        return {}
    ignored = {"compose.yaml", "compose-effective.yaml"}
    result: dict[str, Path] = {}
    for path in sorted(root.rglob("*.yaml")):
        if path.name in ignored:
            continue
        data = load_yaml(path)
        if not isinstance(data, dict):
            continue
        if not {"id", "name", "runtime", "status"}.issubset(data):
            continue
        lab_id = str(data["id"])
        if lab_id in result:
            raise ValueError(f"duplicate laboratory id {lab_id}: {result[lab_id]} and {path}")
        result[lab_id] = path
    return result


def binding_data() -> dict[str, Any]:
    path = SECURITY_ROOT / "bindings" / "labs.yaml"
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"binding catalog must be an object: {path}")
    return data


def validate_runbooks() -> tuple[list[str], list[str], list[Runbook]]:
    errors: list[str] = []
    warnings: list[str] = []
    entries = load_runbooks()
    all_ids: list[str] = []

    for domain, spec in PACKS.items():
        domain_entries = [item for item in entries if item.domain == domain]
        if len(domain_entries) != spec.expected:
            errors.append(f"{domain}: expected {spec.expected} runbooks, found {len(domain_entries)}")
        schema = json.loads(spec.schema.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for item in domain_entries:
            rid = item.runbook_id
            all_ids.append(rid)
            if not rid:
                errors.append(f"{item.path}: missing metadata.id")
                continue
            if item.path.stem != rid.lower():
                errors.append(f"{item.path}: filename does not match {rid}")
            for issue in validator.iter_errors(item.data):
                errors.append(f"{item.path}: {issue.json_path}: {issue.message}")
            for key, _ in walk(item.data):
                if key in FORBIDDEN_KEYS:
                    errors.append(f"{item.path}: forbidden execution key '{key}'")
            text_values = {
                str(value).strip().lower()
                for _, value in walk(item.data)
                if isinstance(value, str)
            }
            placeholders = LEGACY_PLACEHOLDERS.intersection(text_values)
            if placeholders:
                if domain == "api":
                    warnings.append(
                        f"{item.path}: legacy API evaluation placeholders remain pending calibration"
                    )
                else:
                    errors.append(f"{item.path}: placeholder evaluation content remains")

    duplicates = sorted(value for value, count in Counter(all_ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate runbook ids: {', '.join(duplicates)}")
    return errors, warnings, entries


def validate_campaigns(entries: list[Runbook]) -> tuple[list[str], dict[str, tuple[str, Path, dict[str, Any]]]]:
    errors: list[str] = []
    campaigns = load_campaigns()
    ids_by_domain = {
        domain: {item.runbook_id for item in entries if item.domain == domain}
        for domain in PACKS
    }
    categories_by_domain = {
        domain: {item.category for item in entries if item.domain == domain}
        for domain in PACKS
    }
    for campaign_id, (domain, path, data) in campaigns.items():
        selector = data.get("selection") or data.get("selectors") or {}
        if not isinstance(selector, dict):
            errors.append(f"{path}: selection/selectors must be an object")
            continue
        for rid in selector.get("runbook_ids", []) or []:
            if rid not in ids_by_domain[domain]:
                errors.append(f"{path}: unknown runbook id {rid}")
        for category in selector.get("categories", []) or []:
            if category not in categories_by_domain[domain]:
                errors.append(f"{path}: unknown category {category} for {domain}")
        declared_domain = data.get("domain")
        if declared_domain and declared_domain != domain:
            errors.append(f"{path}: declared domain {declared_domain} does not match {domain}")
        if not campaign_id:
            errors.append(f"{path}: missing campaign id")
    return errors, campaigns


def validate_bindings(campaigns: dict[str, tuple[str, Path, dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    data = binding_data()
    domains = data.get("domains", {})
    if not isinstance(domains, dict):
        return ["security/bindings/labs.yaml: domains must be an object"]
    labs = discover_labs()
    for domain, config in domains.items():
        if domain not in PACKS:
            errors.append(f"binding catalog: unknown domain {domain}")
            continue
        if not isinstance(config, dict):
            errors.append(f"binding catalog: domain {domain} must be an object")
            continue
        expected_pack = str(PACKS[domain].root.relative_to(REPO_ROOT))
        if config.get("pack") != expected_pack:
            errors.append(f"binding catalog: {domain} pack must be {expected_pack}")
        for binding in config.get("laboratories", []) or []:
            if not isinstance(binding, dict):
                errors.append(f"binding catalog: invalid laboratory entry in {domain}")
                continue
            lab_id = str(binding.get("id", ""))
            if not lab_id:
                errors.append(f"binding catalog: empty laboratory id in {domain}")
            elif labs and lab_id not in labs:
                errors.append(f"binding catalog: laboratory {lab_id} is not registered in platform")
            for campaign_id in binding.get("campaigns", []) or []:
                campaign = campaigns.get(str(campaign_id))
                if not campaign:
                    errors.append(f"binding catalog: unknown campaign {campaign_id} for {lab_id}")
                elif campaign[0] != domain:
                    errors.append(
                        f"binding catalog: campaign {campaign_id} belongs to {campaign[0]}, not {domain}"
                    )
    return errors


def perform_validation() -> tuple[list[str], list[str], list[Runbook]]:
    errors, warnings, entries = validate_runbooks()
    campaign_errors, campaigns = validate_campaigns(entries)
    errors.extend(campaign_errors)
    errors.extend(validate_bindings(campaigns))
    return errors, warnings, entries


def cmd_validate(_: argparse.Namespace) -> int:
    errors, warnings, entries = perform_validation()
    if warnings:
        print(
            "WARN\t"
            f"{len(warnings)} legacy API evaluation definitions remain pending calibration"
        )
    if errors:
        for error in errors:
            print(f"FAIL\t{error}")
        return 1
    counts = Counter(item.domain for item in entries)
    print(
        "OK\t"
        + " ".join(f"{domain}={counts[domain]}" for domain in PACKS)
        + f" total={len(entries)} warnings={len(warnings)}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = load_runbooks(args.domain)
    print("id\tdomain\tcategory\tstatus\tpath")
    for item in entries:
        if args.category and item.category != args.category:
            continue
        print(
            f"{item.runbook_id}\t{item.domain}\t{item.category}\t{item.status}\t"
            f"{item.path.relative_to(REPO_ROOT)}"
        )
    return 0


def cmd_labs(_: argparse.Namespace) -> int:
    labs = discover_labs()
    data = binding_data()
    print("laboratory\tdomain\tcalibration\tcampaigns\tmanifest")
    for domain, config in data.get("domains", {}).items():
        for binding in config.get("laboratories", []):
            lab_id = str(binding["id"])
            manifest = labs.get(lab_id)
            print(
                f"{lab_id}\t{domain}\t{binding.get('calibration', '')}\t"
                f"{','.join(binding.get('campaigns', []))}\t"
                f"{manifest.relative_to(REPO_ROOT) if manifest else 'UNRESOLVED'}"
            )
    return 0


def cmd_coverage(_: argparse.Namespace) -> int:
    entries = load_runbooks()
    data = binding_data()
    print("domain\trunbooks\tcategories\tlaboratories\tcalibrated")
    for domain in PACKS:
        domain_entries = [item for item in entries if item.domain == domain]
        bindings = data.get("domains", {}).get(domain, {}).get("laboratories", [])
        calibrated = sum(1 for item in bindings if item.get("calibration") == "calibrated")
        print(
            f"{domain}\t{len(domain_entries)}\t{len({item.category for item in domain_entries})}\t"
            f"{len(bindings)}\t{calibrated}"
        )
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    errors, warnings, entries = perform_validation()
    if errors:
        for error in errors:
            print(f"FAIL\t{error}", file=sys.stderr)
        return 1
    labs = discover_labs()
    bindings = binding_data()
    output = {
        "apiVersion": "security.hex0r.io/v1alpha1",
        "kind": "GeneratedSecurityCatalog",
        "canonical": False,
        "runbooks": [
            {
                "id": item.runbook_id,
                "domain": item.domain,
                "category": item.category,
                "status": item.status,
                "path": item.path.relative_to(REPO_ROOT).as_posix(),
            }
            for item in entries
        ],
        "laboratories": {
            lab_id: path.relative_to(REPO_ROOT).as_posix() for lab_id, path in sorted(labs.items())
        },
        "bindings": bindings.get("domains", {}),
        "warnings": warnings,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"EXPORTED\t{len(entries)} runbooks -> {destination}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate all security packs and platform bindings")
    validate.set_defaults(func=cmd_validate)

    list_cmd = sub.add_parser("list", help="list runbooks")
    list_cmd.add_argument("--domain", choices=sorted(PACKS))
    list_cmd.add_argument("--category")
    list_cmd.set_defaults(func=cmd_list)

    labs = sub.add_parser("labs", help="list laboratory bindings")
    labs.set_defaults(func=cmd_labs)

    coverage = sub.add_parser("coverage", help="show domain coverage summary")
    coverage.set_defaults(func=cmd_coverage)

    catalog = sub.add_parser("catalog", help="generate a disposable combined JSON catalog")
    catalog.add_argument("--output", required=True)
    catalog.set_defaults(func=cmd_catalog)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
