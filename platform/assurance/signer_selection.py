#!/usr/bin/env python3
"""Provider-neutral signer-baseline + candidate-class evaluation (no auto-selection).

Repository-only. This module turns the accepted R1-R8 signer baseline
(docs/architecture/lab-assurance-signer-requirements.md, encoded in
platform/schemas/signer-baseline.schema.json and platform/assurance/signer-baseline.yaml)
into machine-checkable truth, and evaluates the four repository-recognized candidate
classes (KMS/HSM/VAULT/PKCS11) as *evidence records* only.

It deliberately:
- selects NO supplier/product automatically;
- treats PKCS11 as an interface class, never as proof of key custody;
- fails closed when the baseline is missing/unaccepted, or when any candidate is
  marked SELECTED, or when candidate evidence is missing/unverified;
- permits an APPROVED human decision to be staged while the baseline remains
  NO_SELECTION, preserving the deliberate separation between decision and transition;
- requires that explicit CHG-HSL-062 human decision for any future PENDING/SELECTED
  supplier-selection contract;
- keeps trust binding disabled and grants no runtime/promotion authority even when a
  future human selection contract is internally coherent;
- never imports or calls a provider client, key generator, trust-store installer,
  network API or live promotion path.

The live observation verification is delegated to the existing, separately tested
``deployment/runtime-promotion/runtime_signer_attestation.py`` verifier; this module
reuses its schema and the tb1 preflight rather than duplicating them.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"
ASSURANCE_DIR = ROOT / "assurance"
BASELINE_SCHEMA = SCHEMAS_DIR / "signer-baseline.schema.json"
BASELINE_YAML = ASSURANCE_DIR / "signer-baseline.yaml"
SIGNER_HUMAN_DECISION_PATH = ASSURANCE_DIR / "signer_human_decision.py"
TB1_PREFILIGHT_PATH = (
    ROOT.parent
    / "deployment"
    / "runtime-promotion"
    / "tb1_authorization_preflight.py"
)
TB1_ATTESTATION_SCHEMA = (
    ROOT.parent
    / "deployment"
    / "runtime-promotion"
    / "tb1-signer-attestation.schema.json"
)
RUNTIME_DEPLOYMENT_YAML = (
    ROOT.parent
    / "deployment"
    / "runner-runtime"
    / "runtime-deployment.yaml"
)

CANDIDATE_CLASSES = ("KMS", "HSM", "VAULT", "PKCS11")
# PKCS11 is an interface standard, not a custody backend.
INTERFACE_CLASSES = ("PKCS11",)
SELECTABLE_CUSTODY_CLASSES = ("KMS", "HSM", "VAULT")
# A class is only ever a custody proof once explicitly proven by verified evidence.
AUTO_SELECTION_FORBIDDEN = True
# Repository-only baseline with no supplier transition made yet. A human decision may
# be staged while this remains NO_SELECTION, but it grants no trust/runtime authority.
NO_SELECTION = "NO_SELECTION"
PENDING = "PENDING"
SELECTED = "SELECTED"

_FORBIDDEN_RUNTIME_IMPORTS = {
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "boto3",
    "hvac",
    "pkcs11",
    "os",
    "shutil",
}


class SignerBaselineError(ValueError):
    """Fail-closed signer-baseline / candidate-class evaluation violation."""


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tb1_preflight = _load_module(
    "signer_selection_tb1_preflight", TB1_PREFILIGHT_PATH
)
signer_human_decision = _load_module(
    "signer_selection_human_decision", SIGNER_HUMAN_DECISION_PATH
)


@dataclass(frozen=True)
class CandidateClassEvaluation:
    cls: str
    is_custody_proof: bool
    evaluation_status: str
    disqualified: bool
    findings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "class": self.cls,
            "is_custody_proof": self.is_custody_proof,
            "evaluation_status": self.evaluation_status,
            "disqualified": self.disqualified,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class SignerBaselineEvaluation:
    accepted: bool
    provider_neutral: bool
    allows_automatic_supplier_choice: bool
    supplier_selection: str
    selected_class: str | None
    promotion_allowed: bool
    failures: tuple[str, ...]
    candidates: tuple[CandidateClassEvaluation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "provider_neutral": self.provider_neutral,
            "allows_automatic_supplier_choice": self.allows_automatic_supplier_choice,
            "supplier_selection": self.supplier_selection,
            "selected_class": self.selected_class,
            "promotion_allowed": self.promotion_allowed,
            "failures": list(self.failures),
            "candidates": [c.as_dict() for c in self.candidates],
        }


@dataclass(frozen=True)
class SignerSelectionTransitionEvaluation:
    supplier_selection: str
    decision_state: str
    selected_class: str | None
    human_decision_id: str | None
    candidate_evidence_ready: bool
    transition_contract_valid: bool
    trust_binding_allowed: bool
    promotion_allowed: bool
    runtime_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "supplier_selection": self.supplier_selection,
            "decision_state": self.decision_state,
            "selected_class": self.selected_class,
            "human_decision_id": self.human_decision_id,
            "candidate_evidence_ready": self.candidate_evidence_ready,
            "transition_contract_valid": self.transition_contract_valid,
            "trust_binding_allowed": self.trust_binding_allowed,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
        }


def load_baseline_schema() -> dict[str, Any]:
    return yaml.safe_load(BASELINE_SCHEMA.read_text(encoding="utf-8"))


def _validate_baseline_document(document: Mapping[str, Any]) -> None:
    schema = load_baseline_schema()
    errors = sorted(
        jsonschema.Draft7Validator(schema).iter_errors(document),
        key=lambda e: list(e.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(p) for p in first.path) or "<root>"
        raise SignerBaselineError(
            f"signer baseline schema violation at {location}: {first.message}"
        )


def load_baseline(path: Path = BASELINE_YAML) -> dict[str, Any]:
    """Load and JSON-schema validate the accepted signer baseline declaration."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SignerBaselineError("signer baseline document must be a mapping")
    _validate_baseline_document(document)
    return document


def _evaluate_candidate(entry: Mapping[str, Any]) -> CandidateClassEvaluation:
    cls = str(entry.get("class"))
    is_custody_proof = bool(entry.get("is_custody_proof"))
    status = str(entry.get("evaluation_status"))
    findings: list[str] = []

    if cls in INTERFACE_CLASSES and is_custody_proof:
        findings.append(
            f"{cls} is an interface class and cannot be a custody proof"
        )

    if status == "SELECTED":
        # No class may be marked selected automatically or by this evaluator.
        findings.append(f"{cls} is marked SELECTED; supplier selection is a human decision")

    if status in ("EVIDENCE_MISSING", "EVIDENCE_UNVERIFIED"):
        findings.append(f"{cls} candidate evidence is {status}; fails closed")

    disqualified = bool(findings)
    return CandidateClassEvaluation(
        cls=cls,
        is_custody_proof=is_custody_proof,
        evaluation_status=status,
        disqualified=disqualified,
        findings=tuple(findings),
    )


def evaluate_signer_baseline(
    document: Mapping[str, Any] | None = None,
) -> SignerBaselineEvaluation:
    """Evaluate the CURRENT R1-R8 baseline; never accepts a selection transition."""
    if document is None:
        document = load_baseline()

    baseline = document.get("signer_baseline") or {}
    failures: list[str] = []

    accepted = baseline.get("accepted") is True
    provider_neutral = baseline.get("provider_neutral") is True
    allows_auto = baseline.get("allows_automatic_supplier_choice") is True
    supplier_selection = str(baseline.get("supplier_selection", NO_SELECTION))

    if supplier_selection != NO_SELECTION:
        # Selection transitions are evaluated only by the explicit transition guard
        # below, which also requires the CHG-HSL-062 human-decision record.
        failures.append(
            "supplier selection is not NO_SELECTION; use the explicit human decision "
            "selection transition contract, never automatic baseline acceptance"
        )

    if not accepted:
        failures.append("signer baseline R1-R8 is not accepted")
    if not provider_neutral:
        failures.append("signer baseline is not provider-neutral")
    if allows_auto:
        failures.append("signer baseline must not allow automatic supplier choice")

    raw_candidates = document.get("candidate_classes") or []
    candidates = tuple(_evaluate_candidate(c) for c in raw_candidates)

    selected: list[str] = [
        c.cls for c in candidates if c.evaluation_status == "SELECTED"
    ]
    if selected:
        failures.append(
            "candidate class(es) marked SELECTED without a human decision: "
            + ", ".join(selected)
        )
    if any(c.disqualified for c in candidates):
        failures.append("one or more candidate classes are disqualified")

    if failures:
        detail = list(failures)
        for c in candidates:
            if c.disqualified:
                detail.extend(f"{c.cls}: {f}" for f in c.findings)
        raise SignerBaselineError(
            "signer baseline evaluation failed closed: " + "; ".join(detail)
        )

    return SignerBaselineEvaluation(
        accepted=accepted,
        provider_neutral=provider_neutral,
        allows_automatic_supplier_choice=allows_auto,
        supplier_selection=supplier_selection,
        selected_class=None,
        promotion_allowed=False,
        failures=(),
        candidates=candidates,
    )


def _load_runtime_deployment(
    runtime_deployment: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if runtime_deployment is None:
        text = RUNTIME_DEPLOYMENT_YAML.read_text(encoding="utf-8")
        runtime_deployment = yaml.safe_load(text)
    if not isinstance(runtime_deployment, Mapping):
        raise SignerBaselineError("runtime deployment document must be a mapping")
    return runtime_deployment


def _validate_inactive_trust_binding(
    runtime_deployment: Mapping[str, Any], *, context: str
) -> None:
    trust_binding = runtime_deployment.get("trust_binding")
    if not isinstance(trust_binding, Mapping):
        raise SignerBaselineError(
            "runtime deployment trust_binding must be a mapping"
        )

    violations: list[str] = []
    if trust_binding.get("enabled") is not False:
        violations.append(
            f"trust_binding.enabled must be False under {context}, "
            f"got {trust_binding.get('enabled')!r}"
        )
    if trust_binding.get("source") is not None:
        violations.append(
            f"trust_binding.source must be None under {context}, "
            f"got {trust_binding.get('source')!r}"
        )
    if trust_binding.get("public_source") is not False:
        violations.append(
            f"trust_binding.public_source must be False under {context}, "
            f"got {trust_binding.get('public_source')!r}"
        )
    if trust_binding.get("expected_sha256") is not None:
        violations.append(
            f"trust_binding.expected_sha256 must be None under {context}, "
            f"got {trust_binding.get('expected_sha256')!r}"
        )

    if violations:
        raise SignerBaselineError(
            f"{context} trust guard failed closed: " + "; ".join(violations)
        )


def validate_no_selection_trust_guard(
    document: Mapping[str, Any] | None = None,
    runtime_deployment: Mapping[str, Any] | None = None,
) -> None:
    """Fail-closed trust-bearing guard for the CURRENT NO_SELECTION contract."""
    if document is None:
        document = load_baseline()
    baseline = document.get("signer_baseline") or {}
    supplier_selection = str(baseline.get("supplier_selection", NO_SELECTION))
    if supplier_selection != NO_SELECTION:
        raise SignerBaselineError(
            "supplier selection is not NO_SELECTION; use the explicit human decision "
            "selection transition contract"
        )

    loaded_runtime = _load_runtime_deployment(runtime_deployment)
    _validate_inactive_trust_binding(loaded_runtime, context=NO_SELECTION)
    return None


def validate_selection_transition_contract(
    document: Mapping[str, Any] | None = None,
    human_decision: Mapping[str, Any] | None = None,
    runtime_deployment: Mapping[str, Any] | None = None,
) -> SignerSelectionTransitionEvaluation:
    """Validate selection-state/decision/evidence coherence without granting authority.

    This is a repository-only *contract* gate. It never chooses a class and it never
    verifies provider evidence itself. An APPROVED human decision may be staged while
    the baseline remains NO_SELECTION; this is deliberately separate from changing the
    baseline to PENDING/SELECTED. A future PENDING/SELECTED state is coherent only after
    that human decision is APPROVED and the matching custody candidate has already
    reached EVIDENCE_VERIFIED_PENDING_DECISION with capability evidence.

    Even then, CHG-HSL-063 requires trust_binding to remain inactive. Trust binding and
    live promotion are separate later changes with their own evidence and approval.
    """
    if document is None:
        document = load_baseline()
    if not isinstance(document, Mapping):
        raise SignerBaselineError("signer baseline document must be a mapping")
    _validate_baseline_document(document)

    if human_decision is None:
        human_decision = signer_human_decision.load_decision()
    try:
        decision_eval = signer_human_decision.evaluate_human_decision(human_decision)
    except signer_human_decision.SignerHumanDecisionError as exc:
        raise SignerBaselineError(
            f"human signer decision failed closed: {exc}"
        ) from exc

    baseline = document.get("signer_baseline") or {}
    supplier_selection = str(baseline.get("supplier_selection", NO_SELECTION))
    selected_class = baseline.get("selected_class")
    human_decision_id = baseline.get("human_decision_id")
    loaded_runtime = _load_runtime_deployment(runtime_deployment)

    if supplier_selection == NO_SELECTION:
        # Both NO_DECISION and APPROVED are legitimate staging states here. The baseline
        # remains intentionally unbound until a separate PENDING/SELECTED transition.
        if decision_eval.state not in (
            signer_human_decision.NO_DECISION,
            signer_human_decision.APPROVED,
        ):
            raise SignerBaselineError(
                f"unsupported signer human decision state under NO_SELECTION: {decision_eval.state}"
            )
        _validate_inactive_trust_binding(loaded_runtime, context=NO_SELECTION)
        return SignerSelectionTransitionEvaluation(
            supplier_selection=NO_SELECTION,
            decision_state=decision_eval.state,
            selected_class=None,
            human_decision_id=None,
            candidate_evidence_ready=False,
            transition_contract_valid=True,
            trust_binding_allowed=False,
            promotion_allowed=False,
            runtime_status="NOT_RUN",
        )

    if supplier_selection not in (PENDING, SELECTED):
        raise SignerBaselineError(
            f"unsupported supplier_selection state: {supplier_selection}"
        )
    if decision_eval.state != signer_human_decision.APPROVED:
        raise SignerBaselineError(
            f"{supplier_selection} requires an APPROVED human signer decision"
        )
    if selected_class not in SELECTABLE_CUSTODY_CLASSES:
        raise SignerBaselineError(
            f"selected_class is not an approved custody class: {selected_class!r}"
        )
    if decision_eval.selected_class != selected_class:
        raise SignerBaselineError(
            "baseline selected_class does not match the APPROVED human decision"
        )
    if decision_eval.decision_id != human_decision_id:
        raise SignerBaselineError(
            "baseline human_decision_id does not match the APPROVED human decision"
        )

    matching = [
        c for c in document.get("candidate_classes", [])
        if c.get("class") == selected_class
    ]
    if len(matching) != 1:
        raise SignerBaselineError(
            f"expected exactly one candidate record for selected_class {selected_class}"
        )
    raw_candidate = matching[0]
    candidate = _evaluate_candidate(raw_candidate)
    if candidate.disqualified:
        raise SignerBaselineError(
            f"selected candidate {selected_class} is disqualified: "
            + "; ".join(candidate.findings)
        )
    if candidate.evaluation_status != "EVIDENCE_VERIFIED_PENDING_DECISION":
        raise SignerBaselineError(
            f"selected candidate {selected_class} evidence is not verified pending decision"
        )
    if not candidate.is_custody_proof:
        raise SignerBaselineError(
            f"selected candidate {selected_class} has no verified custody proof"
        )
    if raw_candidate.get("capability_evidence") is None:
        raise SignerBaselineError(
            f"selected candidate {selected_class} has no capability_evidence record"
        )

    # Selection metadata never performs or implicitly authorizes trust binding.
    _validate_inactive_trust_binding(
        loaded_runtime, context=f"{supplier_selection}_SELECTION_CONTRACT"
    )

    return SignerSelectionTransitionEvaluation(
        supplier_selection=supplier_selection,
        decision_state=decision_eval.state,
        selected_class=str(selected_class),
        human_decision_id=str(human_decision_id),
        candidate_evidence_ready=True,
        transition_contract_valid=True,
        trust_binding_allowed=False,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
    )


def _module_has_no_provider_or_runtime_imports() -> bool:
    source = Path(__file__).read_text(encoding="utf-8")
    for forbidden in _FORBIDDEN_RUNTIME_IMPORTS:
        if f"import {forbidden}" in source or f"from {forbidden}" in source:
            return False
    for forbidden in (
        "load_pem_private_key",
        "load_der_private_key",
        "private_bytes",
        ".sign(",
        "promote(",
        "install_trust_store",
    ):
        if forbidden in source:
            return False
    return True
