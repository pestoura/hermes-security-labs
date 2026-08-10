"""Aggregate read-only evidence gate for the first WebGoat L1 live promotion.

The gate proves repository wiring and fail-closed policy posture. It never
changes a policy, grants execution authority or converts evidence into approval.
Live promotion remains HOLD until the canonical validation campaign is fully
resolved and a separate explicit Human-in-the-Loop promotion decision exists.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = ROOT / "deployment" / "runtime-promotion" / "runtime-promotion-evidence-bundle.yaml"

_REQUIRED_TOP = {
    "schema_version",
    "bundle_id",
    "runtime_status",
    "execution_authority",
    "promotion_mode",
    "candidate",
    "campaign",
    "required_change_records",
    "required_components",
    "fail_closed_policies",
}
_REQUIRED_CANDIDATE = {
    "environment_id",
    "adapter_id",
    "capability_id",
    "intrusiveness_level",
}


class PromotionGateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PromotionGateResult:
    repository_ready: bool
    live_evidence_complete: bool
    promotion_allowed: bool
    recommendation: str
    blockers: tuple[str, ...]
    checked_components: int
    checked_change_records: int
    checked_policies: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository_ready": self.repository_ready,
            "live_evidence_complete": self.live_evidence_complete,
            "promotion_allowed": self.promotion_allowed,
            "recommendation": self.recommendation,
            "blockers": list(self.blockers),
            "checked_components": self.checked_components,
            "checked_change_records": self.checked_change_records,
            "checked_policies": self.checked_policies,
        }


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PromotionGateError(code, f"cannot read {path}") from exc
    if not isinstance(document, dict):
        raise PromotionGateError(code, f"{path} must contain an object")
    return document


def _safe_repo_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise PromotionGateError("BUNDLE_PATH_INVALID", "bundle paths must be relative")
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise PromotionGateError("BUNDLE_PATH_INVALID", "bundle path escapes repository root") from exc
    return candidate


def load_bundle(path: Path = DEFAULT_BUNDLE) -> dict[str, Any]:
    document = _load_yaml(path, "BUNDLE_UNREADABLE")
    if set(document) != _REQUIRED_TOP:
        raise PromotionGateError("BUNDLE_INVALID", "bundle must contain the exact canonical top-level fields")
    if document.get("schema_version") != "1.0.0":
        raise PromotionGateError("BUNDLE_INVALID", "schema_version must be 1.0.0")
    if document.get("runtime_status") != "NOT_RUN":
        raise PromotionGateError("BUNDLE_INVALID", "runtime_status must remain NOT_RUN")
    if document.get("execution_authority") != "none":
        raise PromotionGateError("BUNDLE_INVALID", "evidence bundle must never claim execution authority")
    if document.get("promotion_mode") != "EVIDENCE_ONLY":
        raise PromotionGateError("BUNDLE_INVALID", "promotion_mode must remain EVIDENCE_ONLY")
    candidate = document.get("candidate")
    if not isinstance(candidate, Mapping) or set(candidate) != _REQUIRED_CANDIDATE:
        raise PromotionGateError("BUNDLE_INVALID", "candidate fields are invalid")
    if candidate.get("environment_id") != "webgoat":
        raise PromotionGateError("BUNDLE_INVALID", "first candidate must remain webgoat")
    if candidate.get("adapter_id") != "webgoat-l1":
        raise PromotionGateError("BUNDLE_INVALID", "adapter_id must be webgoat-l1")
    if candidate.get("capability_id") != "web.discovery.headers":
        raise PromotionGateError("BUNDLE_INVALID", "capability_id must be web.discovery.headers")
    if candidate.get("intrusiveness_level") != "L1":
        raise PromotionGateError("BUNDLE_INVALID", "first candidate must remain L1")
    for key in ("required_change_records", "required_components", "fail_closed_policies"):
        value = document.get(key)
        if not isinstance(value, list) or not value or len(value) != len(set(value)):
            raise PromotionGateError("BUNDLE_INVALID", f"{key} must be a non-empty unique list")
    return document


def _change_record_findings(change_id: str) -> list[str]:
    path = ROOT / "changes" / f"{change_id}.yaml"
    if not path.is_file():
        return [f"missing accepted change record {change_id}"]
    doc = _load_yaml(path, "CHANGE_RECORD_UNREADABLE")
    findings: list[str] = []
    if doc.get("id") != change_id:
        findings.append(f"change record identity mismatch: {change_id}")
    if doc.get("state") != "ACCEPTED":
        findings.append(f"change record {change_id} is not ACCEPTED")
    validation = doc.get("validation")
    if not isinstance(validation, Mapping):
        findings.append(f"change record {change_id} lacks validation evidence")
    else:
        for field in ("targeted", "regression"):
            if validation.get(field) not in {"PASS", "NOT_APPLICABLE"}:
                findings.append(f"change record {change_id} {field} is not accepted")
    return findings


def _policy_findings(path: Path, doc: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    label = str(path.relative_to(ROOT))
    expected = {
        "state": "DISABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
    }
    for key, value in expected.items():
        if doc.get(key) != value:
            findings.append(f"{label}: {key} must remain {value}")
    return findings


def _campaign_state(path: Path) -> tuple[bool, str, list[str]]:
    campaign = _load_yaml(path, "CAMPAIGN_UNREADABLE")
    recommendation = str(campaign.get("promotionRecommendation", "UNKNOWN"))
    blockers: list[str] = []
    observations = campaign.get("observations")
    if not isinstance(observations, list):
        raise PromotionGateError("CAMPAIGN_INVALID", "campaign observations must be a list")
    for observation in observations:
        if not isinstance(observation, Mapping) or not observation.get("required"):
            continue
        if observation.get("result") != "PASS" or observation.get("status") != "RESOLVED":
            blockers.append(str(observation.get("id", "UNKNOWN_OBSERVATION")))
    complete = not blockers
    return complete, recommendation, blockers


def run_gate(bundle: Mapping[str, Any]) -> PromotionGateResult:
    # Reuse load_bundle's validation semantics for callers supplying an in-memory copy.
    if not isinstance(bundle, Mapping) or set(bundle) != _REQUIRED_TOP:
        raise PromotionGateError("BUNDLE_INVALID", "bundle structure is invalid")
    if bundle.get("runtime_status") != "NOT_RUN" or bundle.get("execution_authority") != "none":
        raise PromotionGateError("BUNDLE_INVALID", "bundle must remain non-operational")
    if bundle.get("promotion_mode") != "EVIDENCE_ONLY":
        raise PromotionGateError("BUNDLE_INVALID", "bundle must remain evidence-only")

    findings: list[str] = []
    components = bundle["required_components"]
    changes = bundle["required_change_records"]
    policies = bundle["fail_closed_policies"]

    for value in components:
        path = _safe_repo_path(value)
        if not path.is_file():
            findings.append(f"missing required component {value}")

    for change_id in changes:
        if not isinstance(change_id, str) or not change_id.startswith("CHG-HSL-"):
            findings.append(f"invalid change record identifier {change_id!r}")
            continue
        findings.extend(_change_record_findings(change_id))

    for value in policies:
        path = _safe_repo_path(value)
        if not path.is_file():
            findings.append(f"missing fail-closed policy {value}")
            continue
        findings.extend(_policy_findings(path, _load_yaml(path, "POLICY_UNREADABLE")))

    campaign_path = _safe_repo_path(bundle["campaign"])
    if not campaign_path.is_file():
        raise PromotionGateError("CAMPAIGN_UNREADABLE", "canonical campaign file is missing")
    live_complete, recommendation, live_blockers = _campaign_state(campaign_path)

    if recommendation != "HOLD":
        findings.append("canonical campaign must remain HOLD in the evidence-only bundle")
    if live_complete:
        # Even complete evidence is not an approval. A separate HITL promotion record is required.
        live_blockers = ["HUMAN_PROMOTION_APPROVAL_REQUIRED"]

    repository_ready = not findings
    blockers = tuple(findings + live_blockers)
    return PromotionGateResult(
        repository_ready=repository_ready,
        live_evidence_complete=live_complete,
        promotion_allowed=False,
        recommendation="HOLD",
        blockers=blockers,
        checked_components=len(components),
        checked_change_records=len(changes),
        checked_policies=len(policies),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        bundle = load_bundle(args.bundle)
        result = run_gate(bundle)
    except PromotionGateError as exc:
        if args.json:
            print(json.dumps({"repository_ready": False, "promotion_allowed": False, "code": exc.code, "error": str(exc)}, sort_keys=True))
        else:
            print(f"FAIL-CLOSED [{exc.code}] {exc}")
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        print(
            f"repository_ready={str(result.repository_ready).lower()} "
            f"live_evidence_complete={str(result.live_evidence_complete).lower()} "
            f"promotion_allowed=false recommendation={result.recommendation}"
        )
        for blocker in result.blockers:
            print(f"- {blocker}")
    return 0 if result.repository_ready else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
