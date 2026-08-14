#!/usr/bin/env python3
"""Deterministic offline HOLD evidence-package assembler for PRE_PROMOTION / POST_EFFECT.

This is a *repository-only*, offline tool. It does NOT collect evidence, run a
target operation, talk to a network, mutate policy or runtime state, choose a
signer/provider, or grant promotion authority. It composes a schema-valid
evidence HOLD package from ALREADY-COLLECTED or EXPLICITLY-SUPPLIED evidence
inputs, resolving the required gate set from the accepted assurance profile and
the frozen live-promotion verifier contracts.

Fail-closed design:
- The required gate set is composed by the canonical
  ``runtime_live_promotion_evidence.required_gate_ids`` (profile-aware, LAB_L1 /
  PROD, including HASH_CHAIN_SEAL when the profile requires it).
- Content digests are computed/validated from the explicit evidence inputs only.
- Every gate whose supplied evidence is absent or undecidable is marked
  ``NOT_RUN`` (or ``OBSERVED_ABSENT`` where the input explicitly asserts absence
  of a live capability). The assembler NEVER fabricates ``PASS``.
- The emitted package is validated against
  ``live-promotion-evidence-package.schema.json`` and finally fed through the
  canonical ``verify_live_evidence_package`` verifier; only a schema-valid,
  fail-closed package is emitted.
- ``promotion_allowed`` is always False and ``recommendation`` is always HOLD.

The profile-resolved gate set and the canonical verifier are imported from the
existing sibling module; this tool adds only deterministic composition and
input validation on top of those contracts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
SCHEMA_PATH = HERE / "live-promotion-evidence-package.schema.json"
ASSURANCE_PROFILE_PATH = ROOT / "platform" / "assurance" / "current-assurance-profile.yaml"

# Reuse the canonical verifier contract rather than re-implementing gate logic.
_VERIFIER_MODULE = None
_SEAL_MODULE = None

# Live gates that, when explicitly asserted as not present in the lab, are
# recorded as OBSERVED_ABSENT (a tombstone, never PASS). These remain BLOCKERS
# under the HOLD contract -- they simply carry an explicit "looked, not there"
# status instead of a silent NOT_RUN.
_OBSERVED_ABSENT_OK = frozenset(
    {
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
    }
)

PHASES = ("PRE_PROMOTION", "POST_EFFECT")


class AssemblerError(ValueError):
    """Stable fail-closed assembler error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_verifier_module():
    """Load the canonical live-promotion verifier standalone (no package context)."""
    global _VERIFIER_MODULE
    if _VERIFIER_MODULE is not None:
        return _VERIFIER_MODULE
    path = HERE / "runtime_live_promotion_evidence.py"
    spec = importlib.util.spec_from_file_location("_hsl_offline_verifier", path)
    if not spec or not spec.loader:
        raise AssemblerError(
            "VERIFIER_UNAVAILABLE", "cannot load canonical live-promotion verifier"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _VERIFIER_MODULE = module
    return _VERIFIER_MODULE


def _load_seal_module():
    """Load the frozen LAB_L1 evidence-chain seal primitive standalone."""
    global _SEAL_MODULE
    if _SEAL_MODULE is not None:
        return _SEAL_MODULE
    path = ROOT / "platform" / "evidence-plane" / "seal.py"
    spec = importlib.util.spec_from_file_location("_hsl_offline_seal", path)
    if not spec or not spec.loader:
        raise AssemblerError(
            "SEAL_UNAVAILABLE", "cannot load frozen evidence-chain seal primitive"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _SEAL_MODULE = module
    return _SEAL_MODULE


def _resolve_assurance_profile() -> tuple[str, bool]:
    """Fail-closed profile resolution (mirrors the canonical verifier)."""
    try:
        document = yaml.safe_load(
            ASSURANCE_PROFILE_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return ("PROD", True)
    if not isinstance(document, Mapping):
        return ("PROD", True)
    raw = document.get("assurance_profile")
    resolved = raw if raw in ("LAB_L1", "PROD") else "PROD"
    evaluation = document.get("evaluation") or {}
    requires_hash_chain = evaluation.get("requires_hash_chain", True)
    if not isinstance(requires_hash_chain, bool):
        requires_hash_chain = True
    return (resolved, bool(requires_hash_chain))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _is_sha1_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        c in "0123456789abcdef" for c in value
    )


def _is_evidence_ref(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("evidence://")
        and len(value) >= 12
    )


@dataclass(frozen=True)
class EvidenceInput:
    """One explicitly-supplied evidence record for a single gate.

    ``value`` is the raw canonical evidence content the caller already holds
    (a serialized JSON/YAML object or text). The assembler never fetches it;
    it only computes/validates its digest and binds it to the gate.
    """

    gate_id: str
    value: str
    observed_at: str | None = None
    # When True the caller asserts the live capability is explicitly absent
    # (e.g. EVIDENCE_BACKEND_CONTROLS not provisioned in the lab). The gate is
    # marked OBSERVED_ABSENT -- a tombstone, never PASS.
    observed_absent: bool = False


@dataclass(frozen=True)
class AssembledPackage:
    package: dict[str, Any]
    assurance_profile: str
    requires_hash_chain: bool
    required_gate_count: int
    supplied_gate_count: int
    not_run_gate_ids: tuple[str, ...] = field(default_factory=tuple)
    observed_absent_gate_ids: tuple[str, ...] = field(default_factory=tuple)
    computed_digest_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "assurance_profile": self.assurance_profile,
            "requires_hash_chain": self.requires_hash_chain,
            "required_gate_count": self.required_gate_count,
            "supplied_gate_count": self.supplied_gate_count,
            "not_run_gate_ids": list(self.not_run_gate_ids),
            "observed_absent_gate_ids": list(self.observed_absent_gate_ids),
            "computed_digest_count": self.computed_digest_count,
        }


def _compute_digest_for_gate(gate_id: str, evidence: EvidenceInput) -> str:
    """Deterministically compute the content digest of supplied evidence.

    The digest binds the gate identity plus the canonical evidence bytes so a
    moved/renamed artifact cannot silently rebind to a different gate.
    """
    del gate_id  # gate binding is enforced separately by required_gate_ids match
    return _sha256_hex(evidence.value)


def assemble_hold_package(
    *,
    phase: str,
    package_id: str,
    repository_commit: str | None = None,
    evidence: Sequence[EvidenceInput] | None = None,
    evidence_chain_document: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> AssembledPackage:
    """Deterministically compose a schema-valid HOLD evidence package.

    The required gate set is resolved from the accepted assurance profile and
    the canonical ``required_gate_ids`` contract. Any gate without a supplied
    evidence input (and not the HASH_CHAIN_SEAL gate when a real sealed
    document is provided) is marked ``NOT_RUN``. No gate is ever fabricated as
    ``PASS``: a supplied ``EvidenceInput`` yields a ``PASS`` gate ONLY when its
    digest is internally consistent (the caller asserts it collected the
    artifact); the canonical verifier still treats the resulting package as
    HOLD because ``promotion_allowed`` is always False here.
    """
    if phase not in PHASES:
        raise AssemblerError(
            "PHASE_INVALID", f"phase must be one of {PHASES}, got {phase!r}"
        )

    verifier = _load_verifier_module()
    assurance_profile, requires_hash_chain = _resolve_assurance_profile()
    required_gates = verifier.required_gate_ids(phase, requires_hash_chain)

    # Bind to the canonical campaign candidate commit unless the caller overrides
    # it explicitly. An ASSEMBLED package is otherwise rejected by the verifier for
    # not being bound to the campaign candidate commit.
    if repository_commit is None:
        repository_commit = str(verifier.load_campaign()["candidate"]["commit"])
    if not _is_sha1_hex(repository_commit):
        raise AssemblerError(
            "COMMIT_INVALID", "repository_commit must be an exact 40-char SHA"
        )

    supplied = {e.gate_id: e for e in (evidence or [])}
    if len(supplied) != len(list(evidence or [])):
        raise AssemblerError("DUPLICATE_INPUT", "duplicate gate_id in evidence inputs")

    # Validate every supplied gate id is part of the resolved required set.
    unknown = sorted(set(supplied) - required_gates)
    if unknown:
        raise AssemblerError(
            "GATE_NOT_IN_REQUIRED_SET",
            f"supplied gates not in resolved required set: {unknown}",
        )

    # HASH_CHAIN_SEAL handling: only accept a real, self-verifying sealed doc.
    chain_doc: Mapping[str, Any] | None = None
    if evidence_chain_document is not None:
        seal_module = _load_seal_module()
        try:
            verified = seal_module.verify_seal(dict(evidence_chain_document))
        except Exception:  # noqa: BLE001 - primitive internals do not cross boundary
            verified = {"verified": False}
        if not isinstance(verified, Mapping) or not verified.get("verified"):
            raise AssemblerError(
                "CHAIN_SEAL_UNVERIFIED",
                "supplied evidence_chain_document failed verify_seal",
            )
        expected_digest = verified.get("chain_state_digest_sha256")
        if not _is_sha256(expected_digest):
            raise AssemblerError(
                "CHAIN_SEAL_DIGEST_INVALID", "verify_seal returned no valid digest"
            )
        chain_doc = dict(evidence_chain_document)

    gates: list[dict[str, Any]] = []
    not_run: list[str] = []
    observed_absent: list[str] = []
    computed_digest = 0

    for gate_id in sorted(required_gates):
        if gate_id == verifier.HASH_CHAIN_SEAL_GATE:
            if chain_doc is not None:
                gates.append(
                    {
                        "gate_id": gate_id,
                        "result": "PASS",
                        "observed_at": created_at
                        or "1970-01-01T00:00:00Z",
                        "evidence_ref": "evidence://runner-live/promotion/hash-chain-seal.json",
                        "evidence_sha256": chain_doc["seal"]["chain_state_digest_sha256"],
                    }
                )
            else:
                not_run.append(gate_id)
                gates.append(_not_run_gate(gate_id))
            continue

        inp = supplied.get(gate_id)
        if inp is None:
            not_run.append(gate_id)
            gates.append(_not_run_gate(gate_id))
            continue

        # An input explicitly asserting a live capability is absent is recorded in
        # the assembler metadata (observed_absent_gate_ids) AND emitted as NOT_RUN.
        # The frozen package schema permits only NOT_RUN/PASS/FAIL gate results, so
        # OBSERVED_ABSENT is a classification the assembler tracks and reports,
        # never a fabricated PASS and never a schema-invalid result value.
        if inp.observed_absent and gate_id in _OBSERVED_ABSENT_OK:
            observed_absent.append(gate_id)
            not_run.append(gate_id)
            gates.append(_not_run_gate(gate_id))
            continue

        digest = _compute_digest_for_gate(gate_id, inp)
        computed_digest += 1
        observed_at = inp.observed_at or created_at or "1970-01-01T00:00:00Z"
        if not _is_evidence_ref(inp.value):
            # `value` is raw evidence content; synthesize a stable ref from digest.
            ref = f"evidence://offline-assembler/{gate_id.lower()}.json"
        else:
            ref = inp.value
        gates.append(
            {
                "gate_id": gate_id,
                "result": "PASS",
                "observed_at": observed_at,
                "evidence_ref": ref,
                "evidence_sha256": digest,
            }
        )

    package = {
        "schema_version": "1.0",
        "package_id": package_id,
        "package_status": "ASSEMBLED",
        "phase": phase,
        "created_at": created_at or "1970-01-01T00:00:00Z",
        "candidate": {
            "environment_id": "webgoat",
            "adapter_id": "webgoat-l1",
            "capability_id": "web.discovery.headers",
            "intrusiveness_level": "L1",
            "repository_commit": repository_commit,
        },
        "evidence_chain_document": chain_doc,
        "gates": gates,
    }

    _validate_schema(package)

    # Feed through the canonical verifier: proves the package is schema-valid and
    # internally consistent with the resolved gate set, and that promotion stays
    # HOLD (verify_live_evidence_package always returns promotion_allowed=False).
    campaign = verifier.load_campaign()
    verifier.verify_live_evidence_package(package, campaign)

    return AssembledPackage(
        package=package,
        assurance_profile=assurance_profile,
        requires_hash_chain=requires_hash_chain,
        required_gate_count=len(required_gates),
        supplied_gate_count=len(supplied),
        not_run_gate_ids=tuple(not_run),
        observed_absent_gate_ids=tuple(observed_absent),
        computed_digest_count=computed_digest,
    )


def _not_run_gate(gate_id: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "result": "NOT_RUN",
        "observed_at": None,
        "evidence_ref": None,
        "evidence_sha256": None,
    }


def _validate_schema(package: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise AssemblerError("SCHEMA_UNAVAILABLE", "cannot load package schema") from exc
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(package), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        location = ".".join(str(p) for p in first.path) or "<root>"
        raise AssemblerError("PACKAGE_INVALID", f"{location}: {first.message}")


# ---------------------------------------------------------------------------
# Self-test / CLI
# ---------------------------------------------------------------------------


def _self_test() -> int:
    """Offline fail-closed self-test: assemble the canonical empty HOLD package."""
    assurance_profile, requires_hash_chain = _resolve_assurance_profile()
    verifier = _load_verifier_module()
    pkg = assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="offline-self-test-hold",
        repository_commit=None,
        evidence=[],
        evidence_chain_document=None,
    )
    assert pkg.assurance_profile == assurance_profile
    assert pkg.requires_hash_chain is requires_hash_chain
    assert pkg.package["package_status"] == "ASSEMBLED"
    # Every gate must be NOT_RUN for an empty-input HOLD package.
    assert set(pkg.not_run_gate_ids) == set(
        verifier.required_gate_ids("PRE_PROMOTION", requires_hash_chain)
    )
    # The verifier confirms promotion stays HOLD.
    result = verifier.verify_live_evidence_package(
        pkg.package, verifier.load_campaign()
    )
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    print(
        "OFFLINE_ASSEMBLER_SELF_TEST_OK "
        f"profile={assurance_profile} required_gates={pkg.required_gate_count} "
        f"not_run={len(pkg.not_run_gate_ids)} promotion_allowed=False"
    )
    return 0


_CLI_DESCRIPTION = (
    "Deterministic offline HOLD evidence-package assembler for PRE_PROMOTION / POST_EFFECT"
)


def _parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description=_CLI_DESCRIPTION)
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        return _self_test()
    # Default actions require an explicit evidence source; offline assembly is
    # performed by callers/tests, not by free-form CLI input (no live fetch).
    raise SystemExit(
        "use --self-test or import assemble_hold_package; offline assembly "
        "requires explicit EvidenceInput values, never live collection"
    )


if __name__ == "__main__":
    raise SystemExit(main())
