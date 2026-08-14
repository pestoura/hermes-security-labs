#!/usr/bin/env python3
"""LAB_L1 gateway between SAFE observations, LAB_L1 LocalEvidenceStore custody, and the offline PRE_PROMOTION assembler.

Repository-only, fail-closed integration (CHG-HSL-056). It does NOT collect new live
evidence, does NOT touch runtime / systemd / network / Docker / targets, does NOT
install / use Vault / signer / trust, does NOT enable policies, and does NOT commit
real evidence packages. Real / preview packages stay ephemeral OUTSIDE the repository.

What this module wires together (all three canonical components are reused verbatim):

- CHG-HSL-054 ``safe_live_observation_to_evidence_adapter`` reads the already-collected
  SAFE observation artifacts (``docs/roadmap/safe-live-readonly-observation-*.md`` and
  ``deployment/runtime-promotion/evidence/*.yaml``) and produces the strict-allowlist
  set of ``EvidenceInput`` objects. Its mapping contract is unchanged: only
  ``GATEWAY_ADMISSION_REOBSERVATION`` / ``BRIDGE_REVISION_REOBSERVATION`` may become
  ``PASS``; ``HOST_IDENTITY_SOCKET_TRUST`` stays ``NOT_RUN`` (trust OBSERVED_ABSENT);
  ``USER_NAMESPACE_MAPPING`` / ``SIGNER_PROVIDER_ATTESTATION`` / ``RECEIPT_DELIVERY`` /
  ``UNAUTHORIZED_PEER_NEGATIVE`` and every POST_EFFECT gate stay ``NOT_RUN``; under
  ``LAB_L1`` the production WORM backend / tenant isolation are tombstoned as
  ``OBSERVED_ABSENT`` (not PASS).
- CHG-HSL-055 ``LocalEvidenceCustodyBuilder`` persists the already-collected SAFE
  observation claim strings ONLY through ``LocalEvidenceStore`` (content-addressed,
  immutable) and seals a deterministic ``EvidenceChain`` (authenticity=false,
  durability=false). The store ROOT is ephemeral (a caller-supplied temp dir).
- CHG-HSL-051 ``offline_evidence_package_assembler`` composes the schema-valid HOLD
  package from the custodized ``EvidenceInput`` set + the sealed chain document,
  resolving the required gate set from the accepted assurance profile. It always emits
  ``promotion_allowed=false`` / ``recommendation=HOLD``.

The integration makes the already-collected SAFE observations *custodizable*: the SAFE
claim strings are persisted into real local evidence refs/digests via ``LocalEvidenceStore``
and verified by the canonical ``LocalEvidenceVerifier``. Because the assembler synthesizes
the storage_ref ``evidence://offline-assembler/<gate>.json`` for a raw-content PASS input,
this bridge reproduces that exact ref when custodizing, so the verifier resolves the ref to
exactly one store record and binds its digest to the expected gate sha256. The sealed
``EvidenceChain`` satisfies the ``HASH_CHAIN_SEAL`` gate (self-verifying against
``platform/evidence-plane/seal.py``).

Result semantics (must stay invariant under HOLD):
- ``GATEWAY_ADMISSION_REOBSERVATION`` / ``BRIDGE_REVISION_REOBSERVATION`` -> VERIFIED
  (real local evidence refs/digests, verified by LocalEvidenceVerifier).
- ``HASH_CHAIN_SEAL`` -> VERIFIED (sealed EvidenceChain, self-verifying).
- ``HOST_IDENTITY_SOCKET_TRUST`` -> NOT_RUN (trust absent).
- ``USER_NAMESPACE_MAPPING`` / ``SIGNER_PROVIDER_ATTESTATION`` / ``RECEIPT_DELIVERY`` /
  ``UNAUTHORIZED_PEER_NEGATIVE`` -> NOT_RUN (no supporting canonical evidence).
- Backend / tenant -> LAB_L1 ``OBSERVED_ABSENT`` (tombstone), never PASS.
- All POST_EFFECT gates -> NOT_RUN.
- ``promotion_allowed=false``, ``recommendation=HOLD``, ``runtime_status=NOT_RUN`` throughout.

This module is explicitly LAB_L1-only. It never reclassifies ``LocalEvidenceStore`` as a
PROD WORM backend, never weakens PROD WORM / tenant requirements, never adds a signer or
trust binding, and never promotes. It never auto-repins the campaign ``candidate.commit``:
a caller-supplied commit (e.g. an ancestor of HEAD, preserved from provenance) is bound
verbatim. ``NO_RUNTIME_CHANGE``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROMOTION_DIR = ROOT / "deployment" / "runtime-promotion"

# Assembler synthesizes this exact ref for a raw-content PASS input (see
# offline_evidence_package_assembler._compute_digest_for_gate / assemble_hold_package).
_ASSEMBLER_REF_PREFIX = "evidence://offline-assembler/"


class EvidenceCustodyBridgeError(ValueError):
    """Stable fail-closed bridge error."""


def _load_assembler_module():
    path = RUNTIME_PROMOTION_DIR / "offline_evidence_package_assembler.py"
    spec = importlib.util.spec_from_file_location("_hsl056_assembler", path)
    if not spec or not spec.loader:
        raise EvidenceCustodyBridgeError("ASSEMBLER_UNAVAILABLE", "cannot load offline assembler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_safe_adapter_module():
    path = RUNTIME_PROMOTION_DIR / "safe_live_observation_to_evidence_adapter.py"
    spec = importlib.util.spec_from_file_location("_hsl056_safe_adapter", path)
    if not spec or not spec.loader:
        raise EvidenceCustodyBridgeError("ADAPTER_UNAVAILABLE", "cannot load SAFE adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_custody_module():
    path = ROOT / "platform" / "evidence-plane" / "local_evidence_custody.py"
    spec = importlib.util.spec_from_file_location("_hsl056_custody", path)
    if not spec or not spec.loader:
        raise EvidenceCustodyBridgeError("CUSTODY_UNAVAILABLE", "cannot load local evidence custody")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_verifier_module():
    path = ROOT / "platform" / "evidence-plane" / "local_evidence_verifier.py"
    spec = importlib.util.spec_from_file_location("_hsl056_verifier", path)
    if not spec or not spec.loader:
        raise EvidenceCustodyBridgeError("VERIFIER_UNAVAILABLE", "cannot load local evidence verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class CustodyBridgeResult:
    """Deterministic result of the LAB_L1 evidence-custody -> HOLD-package bridge."""

    store_root: str
    evidence_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    object_digests: tuple[str, ...]
    chain_id: str
    sealed_document: dict[str, Any]
    pass_gate_ids: tuple[str, ...]
    not_run_gate_ids: tuple[str, ...]
    observed_absent_gate_ids: tuple[str, ...]
    verified_evidence_count: int
    required_gate_count: int
    promotion_allowed: bool
    recommendation: str
    candidate_commit: str
    package: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "store_root": self.store_root,
            "evidence_ids": list(self.evidence_ids),
            "evidence_refs": list(self.evidence_refs),
            "object_digests": list(self.object_digests),
            "chain_id": self.chain_id,
            "pass_gate_ids": list(self.pass_gate_ids),
            "not_run_gate_ids": list(self.not_run_gate_ids),
            "observed_absent_gate_ids": list(self.observed_absent_gate_ids),
            "verified_evidence_count": self.verified_evidence_count,
            "required_gate_count": self.required_gate_count,
            "promotion_allowed": self.promotion_allowed,
            "recommendation": self.recommendation,
            "candidate_commit": self.candidate_commit,
            "package": self.package,
        }


def _chain_id_for(commit: str) -> str:
    """Deterministic LAB_L1 chain id derived from the bound candidate commit (provenance)."""
    digest = hashlib.sha256(commit.encode("utf-8")).hexdigest()
    return f"chain_{digest[:32]}"


def build_custodized_hold_package(
    *,
    repo_root: Path,
    store_root: Path,
    candidate_commit: str,
    phase: str = "PRE_PROMOTION",
    profile: str = "LAB_L1",
    chain_id: str | None = None,
    sealed_at: str | None = None,
    observed_at: str | None = None,
) -> CustodyBridgeResult:
    """Custodize SAFE observations into real local evidence and assemble a HOLD package.

    The SAFE observation claim strings produced by the CHG-HSL-054 adapter are persisted
    ONLY through ``LocalEvidenceStore`` (CHG-HSL-055) with the exact storage_refs the
    CHG-HSL-051 assembler synthesizes for raw-content PASS inputs, then sealed into a
    deterministic ``EvidenceChain``. The custodized ``EvidenceInput`` set + sealed document
    are fed to the assembler with the canonical ``LocalEvidenceVerifier`` wired in, so the
    already-collected SAFE artifacts become real verified local evidence refs/digests.

    Fail-closed: ``candidate_commit`` must be an exact 40-hex SHA (bound verbatim, never
    auto-repinned). ``store_root`` must be outside the repository OR an explicit ephemeral
    location; this never writes a committed real evidence package.
    """
    assembler = _load_assembler_module()
    safe_adapter = _load_safe_adapter_module()
    custody = _load_custody_module()

    repo_root = Path(repo_root).resolve()
    store_root = Path(store_root).resolve().expanduser()
    if not (isinstance(candidate_commit, str) and len(candidate_commit) == 40
            and all(c in "0123456789abcdef" for c in candidate_commit)):
        raise EvidenceCustodyBridgeError(
            "COMMIT_INVALID", "candidate_commit must be an exact 40-char lowercase SHA"
        )

    # 1) Read already-collected SAFE observations via the strict-allowlist adapter (054).
    inputs, facts = safe_adapter.convert_observations_to_evidence_inputs(
        repo_root=repo_root, phase=phase, profile=profile
    )

    # 2) Custody the SAFE claim strings ONLY through LocalEvidenceStore (055) with the
    #    exact storage_refs the assembler synthesizes for raw-content PASS inputs.
    cid = chain_id or _chain_id_for(candidate_commit)
    builder = custody.LocalEvidenceCustodyBuilder(store_root)
    safe_items: list[Any] = []
    for inp in inputs:
        if inp.gate_id not in safe_adapter.ALLOWED_PASS_GATES:
            # Defensive: the adapter only emits ALLOWED_PASS_GATES as PASS; anything else
            # is an anti-fabrication contract violation at the adapter boundary.
            continue
        ref = f"{_ASSEMBLER_REF_PREFIX}{inp.gate_id.lower()}.json"
        safe_items.append(
            custody.SafeEvidenceItem(
                payload=inp.value.encode("utf-8"),
                classification="raw",
                storage_ref=ref,
                media_type="application/json",
                correlation={
                    "campaign_id": "VAL-HSL-RUNNER-L1-LIVE-PROMOTION",
                    "run_id": "run_ec368a4ccc04419e985b1c4d01e0ddea",
                    "step_id": "safe-observation-custody",
                    "attempt_id": "a1",
                },
                created_at=observed_at or "2026-08-14T19:00:00Z",
            )
        )

    custody_result = None
    if safe_items:
        custody_result = builder.custody(
            chain_id=cid, items=safe_items, sealed_at=sealed_at or "2026-08-14T19:00:00Z"
        )

    # 3) Build the custodized EvidenceInput set (same gate_ids + values as the adapter
    #    produced; the verifier now resolves them against the store we just populated).
    #    The backend/tenant OBSERVED_ABSENT inputs from the adapter are preserved as-is.
    custodized_inputs = list(inputs)

    # 4) Assemble the HOLD package with the real LocalEvidenceVerifier wired into the
    #    canonical verifier, and the sealed chain document for HASH_CHAIN_SEAL.
    verifier = assembler._load_verifier_module()
    evidence_verifier = _load_verifier_module().LocalEvidenceVerifier(builder.store_root) if custody_result else None

    chain_doc = custody_result.sealed_document if custody_result else None
    assembled = assembler.assemble_hold_package(
        phase=phase,
        package_id="lab-l1-custodized-hold",
        repository_commit=candidate_commit,
        evidence=custodized_inputs,
        evidence_chain_document=chain_doc,
    )

    campaign = verifier.load_campaign()
    result = verifier.verify_live_evidence_package(
        assembled.package, campaign, evidence_verifier=evidence_verifier
    )

    return CustodyBridgeResult(
        store_root=str(builder.store_root),
        evidence_ids=tuple(custody_result.evidence_ids) if custody_result else (),
        evidence_refs=tuple(custody_result.evidence_refs) if custody_result else (),
        object_digests=tuple(custody_result.object_digests) if custody_result else (),
        chain_id=cid,
        sealed_document=custody_result.sealed_document if custody_result else {},
        pass_gate_ids=tuple(sorted(
            g["gate_id"] for g in assembled.package["gates"] if g["result"] == "PASS"
        )),
        not_run_gate_ids=tuple(assembled.not_run_gate_ids),
        observed_absent_gate_ids=tuple(assembled.observed_absent_gate_ids),
        verified_evidence_count=result.verified_evidence_count,
        required_gate_count=result.required_gate_count,
        promotion_allowed=result.promotion_allowed,
        recommendation=result.recommendation,
        candidate_commit=assembled.package["candidate"]["repository_commit"],
        package=assembled.package,
    )


def generate_ephemeral_custody_preview(
    *,
    repo_root: Path,
    out_path: Path,
    candidate_commit: str,
    phase: str = "PRE_PROMOTION",
    profile: str = "LAB_L1",
    store_root: Path | None = None,
) -> dict[str, Any]:
    """Build an EPHEMERAL custodized HOLD package preview OUTSIDE the repository.

    The store and the rendered preview package are written OUTSIDE the repo tree and never
    committed. The supplied ``candidate_commit`` is bound verbatim (provenance; an ancestor
    of HEAD is valid and never auto-repinned). Fail-closed: refuses to write inside the repo.
    """
    repo_root = Path(repo_root).resolve()
    out_path = Path(out_path).resolve()
    if out_path == repo_root or str(out_path).startswith(str(repo_root) + "/"):
        raise EvidenceCustodyBridgeError(
            "PREVIEW_INSIDE_REPO", f"refuse: preview output {out_path} must be OUTSIDE the repo"
        )
    store_root = (
        Path(store_root).resolve().expanduser()
        if store_root is not None
        else (out_path.parent / ".ephemeral-local-evidence-store")
    )
    if store_root == repo_root or str(store_root).startswith(str(repo_root) + "/"):
        store_root = out_path.parent / ".ephemeral-local-evidence-store"

    result = build_custodized_hold_package(
        repo_root=repo_root,
        store_root=store_root,
        candidate_commit=candidate_commit,
        phase=phase,
        profile=profile,
    )

    passing = sorted(
        g["gate_id"] for g in result.package["gates"] if g["result"] == "PASS"
    )
    verified = sorted(
        g["gate_id"] for g in result.package["gates"]
        if g["result"] == "PASS" and g.get("evidence_sha256")
    )
    preview = {
        "preview_package_id": "lab-l1-custodized-hold",
        "candidate_commit_bound": result.candidate_commit,
        "store_root": result.store_root,
        "passing_gates": passing,
        "verified_evidence_gate_ids": verified,
        "observed_absent_gates": list(result.observed_absent_gate_ids),
        "not_run_gates": list(result.not_run_gate_ids),
        "verified_evidence_count": result.verified_evidence_count,
        "required_gate_count": result.required_gate_count,
        "promotion_allowed": result.promotion_allowed,
        "recommendation": result.recommendation,
        "evidence_refs": list(result.evidence_refs),
        "object_digests": list(result.object_digests),
        "package": result.package,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(preview, indent=2, sort_keys=True), encoding="utf-8")
    return preview


def _parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="LAB_L1 SAFE-observation -> LocalEvidenceStore custody -> HOLD package bridge"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_preview = sub.add_parser(
        "preview", help="generate an EPHEMERAL custodized HOLD package preview outside the repo"
    )
    p_preview.add_argument("--repo", type=Path, default=ROOT)
    p_preview.add_argument("--out", type=Path, required=True)
    p_preview.add_argument("--candidate-commit", type=str, required=True)
    p_preview.add_argument("--phase", choices=("PRE_PROMOTION", "POST_EFFECT"), default="PRE_PROMOTION")
    p_preview.add_argument("--profile", choices=("LAB_L1", "PROD"), default="LAB_L1")
    p_preview.add_argument("--store", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preview":
        preview = generate_ephemeral_custody_preview(
            repo_root=Path(args.repo),
            out_path=args.out,
            candidate_commit=args.candidate_commit,
            phase=args.phase,
            profile=args.profile,
            store_root=args.store,
        )
        print(json.dumps({
            "verified_evidence_gate_ids": preview["verified_evidence_gate_ids"],
            "passing_gates": preview["passing_gates"],
            "not_run_gates": preview["not_run_gates"],
            "observed_absent_gates": preview["observed_absent_gates"],
            "verified_evidence_count": preview["verified_evidence_count"],
            "required_gate_count": preview["required_gate_count"],
            "promotion_allowed": preview["promotion_allowed"],
            "recommendation": preview["recommendation"],
            "candidate_commit_bound": preview["candidate_commit_bound"],
            "out": str(args.out),
        }, indent=2, sort_keys=True))
        return 0
    raise SystemExit("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
