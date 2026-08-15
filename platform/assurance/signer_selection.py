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
# A class is only ever a custody proof once explicitly proven by verified evidence.
AUTO_SELECTION_FORBIDDEN = True
# Repository-only baseline with no human supplier decision made yet. Fail-closed
# default for supplier_selection until an explicit decision is recorded.
NO_SELECTION = "NO_SELECTION"

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


def load_baseline_schema() -> dict[str, Any]:
    return yaml.safe_load(BASELINE_SCHEMA.read_text(encoding="utf-8"))


def load_baseline(path: Path = BASELINE_YAML) -> dict[str, Any]:
    """Load and JSON-schema validate the accepted signer baseline declaration."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SignerBaselineError("signer baseline document must be a mapping")
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
    """Evaluate the accepted R1-R8 baseline and the candidate classes, fail closed."""
    if document is None:
        document = load_baseline()

    baseline = document.get("signer_baseline") or {}
    failures: list[str] = []

    accepted = baseline.get("accepted") is True
    provider_neutral = baseline.get("provider_neutral") is True
    allows_auto = baseline.get("allows_automatic_supplier_choice") is True
    supplier_selection = str(baseline.get("supplier_selection", "NO_SELECTION"))

    if supplier_selection != NO_SELECTION:
        # Any transition out of NO_SELECTION to PENDING/SELECTED requires an
        # explicit human decision plus a deliberate contract/guard update. This
        # evaluator must not accept a selection transition automatically.
        failures.append(
            "supplier selection is not NO_SELECTION; a transition to "
            "PENDING/SELECTED requires an explicit human decision and a "
            "deliberate contract/guard update, not automatic acceptance"
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
        selected_class=None,  # never selected by this evaluator
        promotion_allowed=False,
        failures=(),
        candidates=candidates,
    )


def validate_no_selection_trust_guard(
    document: Mapping[str, Any] | None = None,
    runtime_deployment: Mapping[str, Any] | None = None,
) -> None:
    """Fail-closed trust-bearing guard for the CURRENT NO_SELECTION contract.

    Repository-only. This reads committed YAML when arguments are omitted; it
    MUST NOT write, install, bind, generate keys, import trust_binding.py, or
    invoke network/process/runtime, and it must not inspect ``/etc``.

    Safe state (NO_SELECTION) requires *exactly* these facts on the
    ``trust_binding`` mapping:
      - enabled is False
      - source is None
      - public_source is False
      - expected_sha256 is None
    The ``trust_store_path`` value is permitted because it only declares the
    canonical destination, not a binding.
    """
    if document is None:
        document = load_baseline()
    baseline = document.get("signer_baseline") or {}
    supplier_selection = str(baseline.get("supplier_selection", NO_SELECTION))
    if supplier_selection != NO_SELECTION:
        raise SignerBaselineError(
            "supplier selection is not NO_SELECTION; a transition to "
            "PENDING/SELECTED requires an explicit human decision and a "
            "deliberate contract/guard update, not automatic acceptance"
        )

    if runtime_deployment is None:
        text = RUNTIME_DEPLOYMENT_YAML.read_text(encoding="utf-8")
        runtime_deployment = yaml.safe_load(text)
    if not isinstance(runtime_deployment, Mapping):
        raise SignerBaselineError(
            "runtime deployment document must be a mapping"
        )

    trust_binding = runtime_deployment.get("trust_binding")
    if not isinstance(trust_binding, Mapping):
        raise SignerBaselineError(
            "runtime deployment trust_binding must be a mapping"
        )

    violations: list[str] = []
    if trust_binding.get("enabled") is not False:
        violations.append(
            f"trust_binding.enabled must be False under NO_SELECTION, "
            f"got {trust_binding.get('enabled')!r}"
        )
    if trust_binding.get("source") is not None:
        violations.append(
            f"trust_binding.source must be None under NO_SELECTION, "
            f"got {trust_binding.get('source')!r}"
        )
    if trust_binding.get("public_source") is not False:
        violations.append(
            f"trust_binding.public_source must be False under NO_SELECTION, "
            f"got {trust_binding.get('public_source')!r}"
        )
    if trust_binding.get("expected_sha256") is not None:
        violations.append(
            f"trust_binding.expected_sha256 must be None under NO_SELECTION, "
            f"got {trust_binding.get('expected_sha256')!r}"
        )

    if violations:
        raise SignerBaselineError(
            "NO_SELECTION trust guard failed closed: " + "; ".join(violations)
        )
    return None


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
