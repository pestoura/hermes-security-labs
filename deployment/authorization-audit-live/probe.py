#!/usr/bin/env python3
"""Synthetic live proof for authorization-audit Evidence Plane persistence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLATFORM = REPO / "platform"
ADAPTER_PATH = PLATFORM / "runner-authorization" / "authorization_audit_adapter.py"
EVIDENCE = PLATFORM / "evidence-plane"
CUSTODY_PATH = EVIDENCE / "authorization_audit_custody.py"
STORE_PATH = EVIDENCE / "local_store.py"
VERIFIER_PATH = EVIDENCE / "local_evidence_verifier.py"
POLICY_PATH = EVIDENCE / "authorization-audit-custody-policy.yaml"


class LiveProbeError(RuntimeError):
    """Stable fail-closed live probe error."""


def _load(name: str, path: Path) -> Any:
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LiveProbeError("MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cleanup(root: Path) -> bool:
    if root.exists():
        shutil.rmtree(root)
    return not root.exists()


def run_probe(root: str | Path) -> dict[str, object]:
    probe_root = Path(root).expanduser().resolve()
    if probe_root.exists():
        raise LiveProbeError("PROBE_ROOT_EXISTS")

    adapter_mod = _load("chg_hsl_090_adapter", ADAPTER_PATH)
    custody_mod = _load("chg_hsl_090_custody", CUSTODY_PATH)
    store_mod = _load("chg_hsl_090_store", STORE_PATH)
    verifier_mod = _load("chg_hsl_090_verifier", VERIFIER_PATH)
    policy = custody_mod.load_policy(POLICY_PATH)
    if policy.get("state") != "DISABLED" or policy.get("runtime_status") != "NOT_RUN":
        raise LiveProbeError("SOURCE_POLICY_NOT_SAFE")
    effective_policy = dict(policy)
    effective_policy["state"] = "ENABLED"

    owned_root = False
    try:
        custody = custody_mod.AuthorizationAuditCustody(effective_policy)
        store = store_mod.LocalEvidenceStore(probe_root)
        owned_root = True
        recorded_at = _utc_now_z()
        adapter = adapter_mod.CanonicalAuthorizationAuditAdapter(
            chain_id="chain_" + "9" * 32,
            custody=custody,
            evidence_store=store,
            recorded_at_provider=lambda: recorded_at,
        )
        context = adapter_mod.AuthorizationAuditContext(
            campaign_id="synthetic-chg-hsl-090",
            run_id="synthetic-run-090",
            step_id="authorization-audit-persistence",
            attempt_id="attempt-1",
            principal="hermes-authorization",
            correlation_id="synthetic-correlation-090",
        )
        adapter.record_event(
            context=context,
            event_type="REGISTERED",
            phase="REGISTRATION",
            decision="ACCEPT",
            reason_code="SYNTHETIC_CUSTODY_PROBE",
            authorization_ref="tb1-authz:v1:" + "a" * 64,
            duplicate=False,
            capability_id="web.discovery.headers",
            intrusiveness_level="L1",
        )
        sealed = adapter.seal(sealed_at=recorded_at)
        entries = sealed.get("entries", [])
        if len(entries) != 1:
            raise LiveProbeError("AUDIT_ENTRY_COUNT_INVALID")
        evidence_id = entries[0].get("evidence_ref")
        if not isinstance(evidence_id, str):
            raise LiveProbeError("EVIDENCE_BINDING_MISSING")
        record_count = len(list(store.records.glob("ev_*.json")))
        reopened = store_mod.LocalEvidenceStore(probe_root)
        reopen_verified = bool(reopened.verify(evidence_id))
        verifier = verifier_mod.LocalEvidenceVerifier(reopened)
        resolver = custody_mod.EvidenceVerifierChainResolver(verifier)
        audit_chain_verified = bool(adapter.verify(resolver=resolver).get("verified"))
        classification = reopened.get_record(evidence_id).get("classification")
        if not reopen_verified or not audit_chain_verified:
            raise LiveProbeError("PERSISTENCE_VERIFICATION_FAILED")
        if classification != "restricted" or record_count != 1:
            raise LiveProbeError("PERSISTENCE_CONTRACT_INVALID")
        result: dict[str, object] = {
            "schema_version": "hsl.authorization-audit-live-proof/v1",
            "runtime_status": "OBSERVED_SYNTHETIC_CUSTODY",
            "policy_source_state": "DISABLED",
            "effective_probe_state": "ENABLED_EPHEMERAL",
            "custody_persisted": True,
            "reopen_verified": reopen_verified,
            "audit_chain_verified": audit_chain_verified,
            "classification": classification,
            "record_count": record_count,
            "execution_authority": "NONE",
            "promotion_allowed": False,
            "target_effect": "none",
        }
    except LiveProbeError:
        if owned_root:
            _cleanup(probe_root)
        raise
    except Exception as exc:
        if owned_root:
            _cleanup(probe_root)
        raise LiveProbeError("PROBE_FAILED") from exc

    if not _cleanup(probe_root):
        raise LiveProbeError("CLEANUP_FAILED")
    result["cleanup_verified"] = True
    return result

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = run_probe(args.root)
    except LiveProbeError as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"status": "REFUSED", "code": "PROBE_FAILED"}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
