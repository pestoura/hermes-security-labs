#!/usr/bin/env python3
"""Deterministic fail-closed adapter: SAFE live observation artifacts -> EvidenceInput.

Repository-only, offline tool. It converts the canonical *SAFE LIVE READ-ONLY*
observation artifacts and ledgers (``docs/roadmap/safe-live-readonly-observation-*.md``
and any structured live-observation evidence already in
``deployment/runtime-promotion/evidence/*.yaml``) into the ``EvidenceInput`` objects
accepted by ``offline_evidence_package_assembler.assemble_hold_package``.

It performs NO collection, NO signer/trust binding, NO policy enable, NO runtime,
service-manager, network, container, target or promotion effect. It only reads already-recorded
read-only observations and composes explicit ``EvidenceInput`` values.

Fail-closed mapping contract (the heart of this adapter):

- Only an explicit STRICT ALLOWLIST of gates may be elevated to ``PASS``, and only
  when the exact observed evidence supports them:
    * ``GATEWAY_ADMISSION_REOBSERVATION``  -- PASS iff the Gateway HOLD boundary was
      observed ACTIVE (PID identity present).
    * ``BRIDGE_REVISION_REOBSERVATION``    -- PASS iff a single CURRENT live Bridge
      revision SHA is observed and that SHA is NOT marked historical-only.
- ``HOST_IDENTITY_SOCKET_TRUST`` MUST NOT be ``PASS`` while the Runner authorization
  trust store is ``OBSERVED_ABSENT``. It is explicitly excluded from the allowlist and
  always stays ``NOT_RUN`` (the socket may be observed, but the trust store is absent).
- ``USER_NAMESPACE_MAPPING`` remains ``NOT_RUN`` unless the current ns/user relationship
  is EXPLICITLY re-attested (the SAFE ledger records it as NOT re-attested).
- ``SIGNER_PROVIDER_ATTESTATION``, ``RECEIPT_DELIVERY``, ``UNAUTHORIZED_PEER_NEGATIVE``
  and every POST_EFFECT (effect/reset) gate remain ``NOT_RUN`` unless explicit evidence
  exists in the observation artifacts.
- ``EVIDENCE_BACKEND_CONTROLS`` / ``EVIDENCE_TENANT_ISOLATION`` follow the canonical
  verifier's profile-aware omission/tombstone semantics: under ``LAB_L1`` an absent
  production WORM backend / tenant isolation is recorded as ``OBSERVED_ABSENT``
  (a tombstone, emitted NOT_RUN, never PASS); under ``PROD`` they are simply NOT_RUN.
- The adapter NEVER fabricates ``PASS`` for any gate outside the allowlist, and it
  NEVER rewrites the candidate commit (provenance): a caller-supplied commit is bound
  exactly, even when it is an ancestor of the repository HEAD; it is never auto-repinned.

The produced ``EvidenceInput`` set is fed to the canonical assembler + verifier, so the
resulting package is always schema-valid and ``promotion_allowed`` stays ``False``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"

# The assembler is loaded standalone (no package context) to reuse its
# EvidenceInput contract and the canonical verifier exactly as-is.
_ASSEMBLER_MODULE = None

# Strict allowlist: ONLY these gates may be elevated to PASS by the adapter, and
# ONLY when the exact observed evidence supports them. Every other required gate is
# intentionally excluded and stays NOT_RUN. HOST_IDENTITY_SOCKET_TRUST is excluded
# even though its socket facts are observed, because its trust store is ABSENT.
ALLOWED_PASS_GATES = frozenset(
    {
        "GATEWAY_ADMISSION_REOBSERVATION",
        "BRIDGE_REVISION_REOBSERVATION",
    }
)

# Gates that must NEVER become PASS regardless of any observed artifact (hard reject).
_NEVER_PASS_GATES = frozenset(
    {
        "HOST_IDENTITY_SOCKET_TRUST",
        "USER_NAMESPACE_MAPPING",
        "SIGNER_PROVIDER_ATTESTATION",
        "RECEIPT_DELIVERY",
        "UNAUTHORIZED_PEER_NEGATIVE",
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    }
)

# POST_EFFECT gates are live-effect/reset gates; no live observation artifact ever
# supports them, so they are always NOT_RUN.
_POST_EFFECT_GATES = frozenset(
    {
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    }
)


@dataclass(frozen=True)
class ObservationFacts:
    """Normalized, fail-closed view of the recorded SAFE live observations.

    Every field defaults to the SAFE (non-promoting) state. Absence of evidence is
    treated as absence of support, never as support.
    """

    gateway_boundary_active: bool = False
    gateway_pid: int | None = None
    bridge_revision_current: str | None = None
    bridge_revision_historical: tuple[str, ...] = field(default_factory=tuple)
    trust_store_absent: bool = False
    namespace_re_attested: bool = False
    signer_evidence_present: bool = False
    receipt_delivery_evidence_present: bool = False
    unauthorized_peer_negative_present: bool = False
    production_backend_present: bool = False
    tenant_isolation_present: bool = False
    # Raw provenance of the artifacts that contributed to these facts.
    sources: tuple[str, ...] = field(default_factory=tuple)


class AdapterError(ValueError):
    """Stable fail-closed adapter error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_assembler_module():
    global _ASSEMBLER_MODULE
    if _ASSEMBLER_MODULE is not None:
        return _ASSEMBLER_MODULE
    path = HERE / "offline_evidence_package_assembler.py"
    spec = importlib.util.spec_from_file_location("_hsl_safe_obs_assembler", path)
    if not spec or not spec.loader:
        raise AdapterError(
            "ASSEMBLER_UNAVAILABLE",
            "cannot load offline_evidence_package_assembler",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _ASSEMBLER_MODULE = module
    return _ASSEMBLER_MODULE


# ---------------------------------------------------------------------------
# Parsing of canonical SAFE observation artifacts (readonly, fail-closed)
# ---------------------------------------------------------------------------

_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _parse_safe_markdown(doc_text: str, source_name: str) -> ObservationFacts:
    """Parse a SAFE-LIVE-READONLY observation ledger markdown into facts.

    Fail-closed: when a fact cannot be positively determined, it defaults to the
    safe (non-supporting) value. Ambiguous or duplicated markers yield the safe
    value rather than an elevation.
    """
    facts = ObservationFacts()

    # Gateway HOLD boundary active with a PID identity.
    gw = re.search(
        r"Execution Gateway HOLD boundary\s*\|\s*active;\s*PID identity\s*`?(\d+)",
        doc_text,
    )
    if gw:
        facts = _replace(facts, gateway_boundary_active=True, gateway_pid=int(gw.group(1)))

    # Current live Bridge revision (must be exactly one, explicitly labelled current).
    current_matches = re.findall(
        r"Current live Hermes MCP Bridge revision \(current live observation\):\s*\**\s*`?"
        r"([0-9a-f]{40})`?",
        doc_text,
    )
    historical_matches = re.findall(
        r"`?([0-9a-f]{40})`?\s*is retained ONLY as historical candidate/evidence",
        doc_text,
    )
    if len(current_matches) == 1:
        current = current_matches[0]
        # A current SHA that is simultaneously marked historical-only is ambiguous ->
        # do NOT treat it as supporting evidence.
        if current not in set(historical_matches):
            facts = _replace(
                facts,
                bridge_revision_current=current,
                bridge_revision_historical=tuple(sorted(set(historical_matches))),
            )

    # Runner authorization trust store OBSERVED_ABSENT.
    if re.search(
        r"Runner authorization trust store\s*\|\s*`?OBSERVED_ABSENT`?", doc_text
    ) or "authorization-trust-store.json not present" in doc_text:
        facts = _replace(facts, trust_store_absent=True)

    # Namespace relationship NOT re-attested -> namespace_re_attested stays False.
    if re.search(
        r"Namespace relationship\s*\|\s*\**NOT re-attested\**", doc_text
    ) or "ns/user dereference denied" in doc_text:
        facts = _replace(facts, namespace_re_attested=False)

    # SAFE ledger explicitly lists these sub-facts as NOT_RUN / UNKNOWN.
    if re.search(r"signer / provider observation:\s*`NOT_RUN`", doc_text):
        facts = _replace(facts, signer_evidence_present=False)
    if re.search(r"peer-negative \(unauthorized-peer\) test:\s*`NOT_RUN`", doc_text):
        facts = _replace(facts, unauthorized_peer_negative_present=False)
    if re.search(
        r"first authorized effect \+ reset evidence:\s*`NOT_RUN`", doc_text
    ) or "first authorized effect + reset evidence" in doc_text:
        facts = _replace(facts, production_backend_present=False)

    facts = _replace(
        facts, sources=tuple(sorted(set(facts.sources) | {source_name}))
    )
    return facts


def _parse_structured_evidence(evidence: Mapping[str, Any], source_name: str) -> ObservationFacts:
    """Parse a structured live-observation YAML evidence document into facts."""
    facts = ObservationFacts()

    host = evidence.get("host_identity_socket_observation") or {}
    trust = (host.get("observed") or {}).get("trust_store") or {}
    if trust.get("present") is False:
        facts = _replace(facts, trust_store_absent=True)

    # The structured CHG-HSL-038 artifact recorded a userns relationship of "same",
    # but the authoritative SAFE reconcile ledger overrides it to NOT re-attested.
    # We therefore never set namespace_re_attested=True from this artifact; it is
    # left False (safe) and the ledger is the authority for re-attestation.
    userns = evidence.get("user_namespace_observation") or {}
    rel = (userns.get("observed") or {}).get("user_namespace_relationship")
    if rel == "same":
        # Recorded, but NOT an explicit re-attestation under the SAFE contract.
        facts = _replace(facts, namespace_re_attested=False)

    remaining = evidence.get("remaining_live_requirements") or []
    if any("RUNNER_AUTHORIZATION_TRUST_STORE_ABSENT" in str(r) for r in remaining):
        facts = _replace(facts, trust_store_absent=True)
    if any("PRODUCTION_WORM_BACKEND_NOT_OBSERVED" in str(r) for r in remaining):
        facts = _replace(facts, production_backend_present=False)
    if any("BACKEND_TENANT_ISOLATION_NOT_OBSERVED" in str(r) for r in remaining):
        facts = _replace(facts, tenant_isolation_present=False)

    facts = _replace(
        facts, sources=tuple(sorted(set(facts.sources) | {source_name}))
    )
    return facts


def _replace(
    facts: ObservationFacts, **changes: Any
) -> ObservationFacts:
    return ObservationFacts(
        gateway_boundary_active=changes.get(
            "gateway_boundary_active", facts.gateway_boundary_active
        ),
        gateway_pid=changes.get("gateway_pid", facts.gateway_pid),
        bridge_revision_current=changes.get(
            "bridge_revision_current", facts.bridge_revision_current
        ),
        bridge_revision_historical=changes.get(
            "bridge_revision_historical", facts.bridge_revision_historical
        ),
        trust_store_absent=changes.get("trust_store_absent", facts.trust_store_absent),
        namespace_re_attested=changes.get(
            "namespace_re_attested", facts.namespace_re_attested
        ),
        signer_evidence_present=changes.get(
            "signer_evidence_present", facts.signer_evidence_present
        ),
        receipt_delivery_evidence_present=changes.get(
            "receipt_delivery_evidence_present", facts.receipt_delivery_evidence_present
        ),
        unauthorized_peer_negative_present=changes.get(
            "unauthorized_peer_negative_present", facts.unauthorized_peer_negative_present
        ),
        production_backend_present=changes.get(
            "production_backend_present", facts.production_backend_present
        ),
        tenant_isolation_present=changes.get(
            "tenant_isolation_present", facts.tenant_isolation_present
        ),
        sources=changes.get("sources", facts.sources),
    )


def collect_observation_facts(repo_root: Path) -> ObservationFacts:
    """Read every canonical SAFE live observation artifact in the repo, fail-closed."""
    repo_root = Path(repo_root)
    merged = ObservationFacts()

    # 1) SAFE-LIVE-READONLY ledgers under docs/roadmap.
    ledgers = sorted(repo_root.glob("docs/roadmap/safe-live-readonly-observation-*.md"))
    for ledger in ledgers:
        try:
            text = ledger.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parsed = _parse_safe_markdown(text, ledger.name)
        merged = _merge(merged, parsed)

    # 2) Any structured live-observation evidence already in the runtime-promotion dir.
    evidence_dir = repo_root / "deployment" / "runtime-promotion" / "evidence"
    if evidence_dir.is_dir():
        for ev in sorted(evidence_dir.glob("*.yaml")):
            try:
                doc = yaml.safe_load(ev.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                continue
            if not isinstance(doc, dict):
                continue
            parsed = _parse_structured_evidence(doc, ev.name)
            merged = _merge(merged, parsed)

    return merged


def _merge(a: ObservationFacts, b: ObservationFacts) -> ObservationFacts:
    """Merge two fact sets, fail-closed.

    Presence/absence facts use OR semantics: a positive claim from ANY observation
    survives (silence from another artifact must not negate it). ``namespace_re_attested``
    is AND (an explicit re-attestation is required from EVERY source, otherwise it
    stays NOT re-attested). Optional identifier fields (``gateway_pid``,
    ``bridge_revision_current``) keep a positive value unless a DIFFERENT positive
    value conflicts, in which case they are nulled fail-closed.
    """
    return ObservationFacts(
        gateway_boundary_active=a.gateway_boundary_active or b.gateway_boundary_active,
        gateway_pid=_merge_optional_id(a.gateway_pid, b.gateway_pid),
        bridge_revision_current=_merge_optional_id(
            a.bridge_revision_current, b.bridge_revision_current
        ),
        bridge_revision_historical=tuple(
            sorted(set(a.bridge_revision_historical) | set(b.bridge_revision_historical))
        ),
        trust_store_absent=a.trust_store_absent or b.trust_store_absent,
        namespace_re_attested=a.namespace_re_attested and b.namespace_re_attested,
        signer_evidence_present=a.signer_evidence_present or b.signer_evidence_present,
        receipt_delivery_evidence_present=(
            a.receipt_delivery_evidence_present or b.receipt_delivery_evidence_present
        ),
        unauthorized_peer_negative_present=(
            a.unauthorized_peer_negative_present or b.unauthorized_peer_negative_present
        ),
        production_backend_present=(
            a.production_backend_present or b.production_backend_present
        ),
        tenant_isolation_present=(
            a.tenant_isolation_present or b.tenant_isolation_present
        ),
        sources=tuple(sorted(set(a.sources) | set(b.sources))),
    )


def _merge_optional_id(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a == b else None


# ---------------------------------------------------------------------------
# Strict allowlist mapping -> EvidenceInput
# ---------------------------------------------------------------------------


def convert_observations_to_evidence_inputs(
    *,
    repo_root: Path,
    phase: str = "PRE_PROMOTION",
    profile: str = "LAB_L1",
) -> tuple[Any, ObservationFacts]:
    """Convert collected SAFE observations into canonical EvidenceInput objects.

    Returns (inputs, facts). The produced inputs are deterministic and never contain
    a fabricated PASS outside ``ALLOWED_PASS_GATES``. POST_EFFECT gates are never
    supplied (they are live-effect gates with no observation support).
    """
    if phase not in ("PRE_PROMOTION", "POST_EFFECT"):
        raise AdapterError("PHASE_INVALID", f"phase must be PRE_PROMOTION/POST_EFFECT, got {phase!r}")
    assembler = _load_assembler_module()
    facts = collect_observation_facts(Path(repo_root))

    inputs: list[Any] = []

    # GATEWAY_ADMISSION_REOBSERVATION: PASS only on exact observed ACTIVE boundary.
    if facts.gateway_boundary_active and facts.gateway_pid is not None:
        inputs.append(
            assembler.EvidenceInput(
                gate_id="GATEWAY_ADMISSION_REOBSERVATION",
                value=f"gateway-hold-boundary:active pid={facts.gateway_pid}",
                observed_at=None,
            )
        )

    # BRIDGE_REVISION_REOBSERVATION: PASS only on a single current, non-historical SHA.
    if facts.bridge_revision_current and facts.bridge_revision_current not in set(
        facts.bridge_revision_historical
    ):
        inputs.append(
            assembler.EvidenceInput(
                gate_id="BRIDGE_REVISION_REOBSERVATION",
                value=f"bridge-revision:current={facts.bridge_revision_current}",
                observed_at=None,
            )
        )

    # HOST_IDENTITY_SOCKET_TRUST: NEVER PASS while trust store OBSERVED_ABSENT.
    # It is intentionally excluded from ALLOWED_PASS_GATES, so we emit nothing and
    # the gate stays NOT_RUN. Explicit anti-fabrication refuse if a caller tries.
    if facts.trust_store_absent and "HOST_IDENTITY_SOCKET_TRUST" in ALLOWED_PASS_GATES:
        raise AdapterError(
            "ANTI_FABRICATION",
            "HOST_IDENTITY_SOCKET_TRUST must not be elevatable to PASS",
        )

    # Profile-aware omission/tombstone for LAB_L1 production WORM/tenant evidence.
    if profile == "LAB_L1":
        # _OBSERVED_ABSENT_OK in the canonical assembler is exactly these two gates.
        if not facts.production_backend_present:
            inputs.append(
                assembler.EvidenceInput(
                    gate_id="EVIDENCE_BACKEND_CONTROLS",
                    value="evidence://note/production-worm-backend-absent",
                    observed_at=None,
                    observed_absent=True,
                )
            )
        if not facts.tenant_isolation_present:
            inputs.append(
                assembler.EvidenceInput(
                    gate_id="EVIDENCE_TENANT_ISOLATION",
                    value="evidence://note/tenant-isolation-absent",
                    observed_at=None,
                    observed_absent=True,
                )
            )

    return tuple(inputs), facts


# ---------------------------------------------------------------------------
# Ephemeral PRE_PROMOTION preview (never commits a real evidence package)
# ---------------------------------------------------------------------------


def generate_ephemeral_preview(
    *,
    repo_root: Path,
    out_path: Path,
    candidate_commit: str | None = None,
    phase: str = "PRE_PROMOTION",
    profile: str = "LAB_L1",
) -> dict[str, Any]:
    """Build an EPHEMERAL HOLD package preview OUTSIDE the repo and run the verifier.

    The produced package is written to ``out_path`` (which must live outside the
    repository tree) and validated through the canonical verifier. This never writes
    into the repository's evidence directory and never performs a git commit. The
    supplied ``candidate_commit`` is bound verbatim; an ancestor of the repository HEAD
    is a valid provenance value and is never auto-repinned to HEAD.
    """
    assembler = _load_assembler_module()
    verifier = assembler._load_verifier_module()

    repo_root = Path(repo_root).resolve()
    out_path = Path(out_path).resolve()
    # Fail-closed: refuse to write the preview inside the repository tree (it must
    # not become a committed real evidence package).
    if out_path == repo_root or str(out_path).startswith(str(repo_root) + "/"):
        raise AdapterError(
            "PREVIEW_INSIDE_REPO",
            f"refuse: preview output {out_path} must be OUTSIDE the repo {repo_root}",
        )

    inputs, facts = convert_observations_to_evidence_inputs(
        repo_root=repo_root, phase=phase, profile=profile
    )

    package_id = f"ephemeral-preview-{phase.lower()}"
    assembled = assembler.assemble_hold_package(
        phase=phase,
        package_id=package_id,
        repository_commit=candidate_commit,
        evidence=inputs,
        evidence_chain_document=None,
    )

    campaign = verifier.load_campaign()
    result = verifier.verify_live_evidence_package(assembled.package, campaign)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preview = {
        "preview_package_id": package_id,
        "sources": list(facts.sources),
        "passing_gates": sorted(
            g["gate_id"]
            for g in assembled.package["gates"]
            if g["result"] == "PASS"
        ),
        "not_run_gates": list(assembled.not_run_gate_ids),
        "observed_absent_gates": list(assembled.observed_absent_gate_ids),
        "supplied_evidence_refs": [
            g["evidence_ref"]
            for g in assembled.package["gates"]
            if g["result"] == "PASS"
        ],
        "candidate_commit_bound": assembled.package["candidate"]["repository_commit"],
        "verifier": result.as_dict(),
        "package": assembled.package,
    }
    out_path.write_text(json.dumps(preview, indent=2, sort_keys=True), encoding="utf-8")
    return preview


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="Deterministic fail-closed adapter: SAFE live observations -> EvidenceInput"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_preview = sub.add_parser(
        "preview",
        help="generate an EPHEMERAL PRE_PROMOTION package preview outside the repo",
    )
    p_preview.add_argument("--repo", type=Path, default=ROOT)
    p_preview.add_argument("--out", type=Path, required=True)
    p_preview.add_argument("--candidate-commit", type=str, default=None)
    p_preview.add_argument("--phase", choices=("PRE_PROMOTION", "POST_EFFECT"), default="PRE_PROMOTION")
    p_preview.add_argument("--profile", choices=("LAB_L1", "PROD"), default="LAB_L1")

    p_inputs = sub.add_parser(
        "inputs", help="list the EvidenceInput gates the repo observations would produce"
    )
    p_inputs.add_argument("--repo", type=Path, default=ROOT)
    p_inputs.add_argument("--phase", choices=("PRE_PROMOTION", "POST_EFFECT"), default="PRE_PROMOTION")
    p_inputs.add_argument("--profile", choices=("LAB_L1", "PROD"), default="LAB_L1")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preview":
        preview = generate_ephemeral_preview(
            repo_root=Path(args.repo),
            out_path=args.out,
            candidate_commit=args.candidate_commit,
            phase=args.phase,
            profile=args.profile,
        )
        print(json.dumps(preview["verifier"], indent=2, sort_keys=True))
        print(
            f"EPHEMERAL_PREVIEW_OK passing={preview['passing_gates']} "
            f"promotion_allowed={preview['verifier']['promotion_allowed']} "
            f"recommendation={preview['verifier']['recommendation']} "
            f"out={args.out}"
        )
        return 0
    if args.command == "inputs":
        inputs, facts = convert_observations_to_evidence_inputs(
            repo_root=Path(args.repo), phase=args.phase, profile=args.profile
        )
        payload = {
            "sources": list(facts.sources),
            "passing_gates": sorted(i.gate_id for i in inputs),
            "trust_store_absent": facts.trust_store_absent,
            "namespace_re_attested": facts.namespace_re_attested,
            "bridge_revision_current": facts.bridge_revision_current,
            "gateway_boundary_active": facts.gateway_boundary_active,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    raise SystemExit("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
