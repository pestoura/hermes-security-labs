from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_live_promotion_evidence.py"
)
PACKAGE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "live-promotion-evidence-package.example.yaml"
)
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = _load("runtime_live_promotion_evidence_test", MODULE_PATH)


def _campaign() -> dict[str, Any]:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _digest(gate_id: str) -> str:
    return hashlib.sha256(f"evidence:{gate_id}".encode()).hexdigest()


def _assembled(phase: str) -> dict[str, Any]:
    gates = []
    for gate_id in sorted(live.REQUIRED_GATES[phase]):
        gates.append(
            {
                "gate_id": gate_id,
                "result": "PASS",
                "observed_at": _now(),
                "evidence_ref": f"evidence://runner-live/promotion/{gate_id.lower()}.json",
                "evidence_sha256": _digest(gate_id),
            }
        )
    return {
        "schema_version": "1.0",
        "package_id": f"webgoat-l1-{phase.lower()}-fixture",
        "package_status": "ASSEMBLED",
        "phase": phase,
        "created_at": _now(),
        "candidate": {
            "environment_id": "webgoat",
            "adapter_id": "webgoat-l1",
            "capability_id": "web.discovery.headers",
            "intrusiveness_level": "L1",
            "repository_commit": _campaign()["candidate"]["commit"],
        },
        "gates": gates,
    }


class StaticEvidenceVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str]] = []

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        self.calls.append((evidence_ref, sha256))
        return self.accepted and evidence_ref.startswith("evidence://") and len(sha256) == 64


def test_committed_example_is_inert_and_incomplete() -> None:
    package = live.load_package(PACKAGE_PATH)
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.package_valid is True
    assert result.package_complete is False
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "EVIDENCE_COLLECTION_REQUIRED"
    assert result.required_gate_count == len(live.PRE_PROMOTION_GATES)
    assert all(blocker.endswith(":NOT_RUN") for blocker in result.blockers)


def test_complete_pre_promotion_package_requires_human_review_not_promotion() -> None:
    verifier = StaticEvidenceVerifier()
    package = _assembled("PRE_PROMOTION")
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=verifier
    )
    assert result.package_complete is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "HUMAN_PROMOTION_REVIEW_REQUIRED"
    assert result.verified_evidence_count == len(live.PRE_PROMOTION_GATES)
    assert result.blockers == ()


def test_complete_post_effect_package_requires_campaign_acceptance_review() -> None:
    verifier = StaticEvidenceVerifier()
    package = _assembled("POST_EFFECT")
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=verifier
    )
    assert result.package_complete is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED"
    assert result.verified_evidence_count == len(live.POST_EFFECT_GATES)


def test_default_verifier_refuses_self_declared_pass_evidence() -> None:
    result = live.verify_live_evidence_package(_assembled("PRE_PROMOTION"), _campaign())
    assert result.package_complete is False
    assert result.verified_evidence_count == 0
    assert all("EVIDENCE_UNVERIFIED" in blocker for blocker in result.blockers)


def test_verified_fail_is_valid_evidence_but_blocks_phase() -> None:
    package = _assembled("PRE_PROMOTION")
    gate = next(item for item in package["gates"] if item["gate_id"] == "UNAUTHORIZED_PEER_NEGATIVE")
    gate["result"] = "FAIL"
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.package_valid is True
    assert result.package_complete is False
    assert "UNAUTHORIZED_PEER_NEGATIVE:FAIL" in result.blockers
    assert not any(
        blocker == "UNAUTHORIZED_PEER_NEGATIVE:EVIDENCE_UNVERIFIED"
        for blocker in result.blockers
    )


def test_not_run_gate_blocks_assembled_phase() -> None:
    package = _assembled("PRE_PROMOTION")
    gate = next(item for item in package["gates"] if item["gate_id"] == "RECEIPT_DELIVERY")
    gate.update(
        {
            "result": "NOT_RUN",
            "observed_at": None,
            "evidence_ref": None,
            "evidence_sha256": None,
        }
    )
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.package_complete is False
    assert "RECEIPT_DELIVERY:NOT_RUN" in result.blockers


def test_assembled_package_must_bind_exact_campaign_commit() -> None:
    package = _assembled("PRE_PROMOTION")
    package["candidate"]["repository_commit"] = "f" * 40
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(
            package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code == "PACKAGE_CANDIDATE_MISMATCH"


def test_phase_gate_set_is_exact_and_cannot_skip_human_decision() -> None:
    package = _assembled("POST_EFFECT")
    package["gates"] = [
        item for item in package["gates"] if item["gate_id"] != "HITL_PROMOTION_DECISION"
    ]
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(
            package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_extra_gate_is_rejected_instead_of_silently_ignored() -> None:
    package = _assembled("PRE_PROMOTION")
    extra = copy.deepcopy(package["gates"][0])
    extra["gate_id"] = "UNDECLARED_GATE"
    package["gates"].append(extra)
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(
            package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_duplicate_gate_is_rejected() -> None:
    package = _assembled("PRE_PROMOTION")
    package["gates"].append(copy.deepcopy(package["gates"][0]))
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(
            package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code == "PACKAGE_INVALID"


def test_not_run_package_cannot_smuggle_executed_gate() -> None:
    package = live.load_package(PACKAGE_PATH)
    package["gates"][0] = {
        "gate_id": package["gates"][0]["gate_id"],
        "result": "PASS",
        "observed_at": _now(),
        "evidence_ref": "evidence://runner-live/promotion/smuggled.json",
        "evidence_sha256": hashlib.sha256(b"smuggled").hexdigest(),
    }
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(
            package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
        )
    assert exc.value.code == "PACKAGE_INVALID"


def test_cli_returns_red_for_incomplete_committed_example() -> None:
    assert live.main(["--package", str(PACKAGE_PATH), "check"]) == 2


def test_source_has_no_collection_mutation_or_target_execution_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "requests",
        "http.client",
        "socket",
        "subprocess",
        "docker",
        "boto3",
        "azure.storage",
        "google.cloud",
        "os.chmod",
        "os.chown",
        ".sign(",
    ):
        assert forbidden not in source
    assert "DenyAllEvidenceVerifier" in source
    assert "promotion_allowed=False" in source
    assert 'recommendation="HOLD"' in source
