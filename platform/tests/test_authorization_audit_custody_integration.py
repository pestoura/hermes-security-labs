from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_AUTH = ROOT / "platform" / "runner-authorization"
EVIDENCE = ROOT / "platform" / "evidence-plane"
ADAPTER_PATH = RUNNER_AUTH / "authorization_audit_adapter.py"
CUSTODY_PATH = EVIDENCE / "authorization_audit_custody.py"
POLICY_PATH = EVIDENCE / "authorization-audit-custody-policy.yaml"
STORE_PATH = EVIDENCE / "local_store.py"
VERIFIER_PATH = EVIDENCE / "local_evidence_verifier.py"


def _load(path: Path, name: str) -> Any:
    assert path.exists(), f"{path.name} is not implemented yet"
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _adapter() -> Any:
    return _load(ADAPTER_PATH, "chg_hsl_079_integration_authorization_audit_adapter")


def _custody() -> Any:
    return _load(CUSTODY_PATH, "chg_hsl_079_integration_authorization_audit_custody")


def _store_module() -> Any:
    return _load(STORE_PATH, "chg_hsl_079_integration_local_store")


def _verifier_module() -> Any:
    return _load(VERIFIER_PATH, "chg_hsl_079_integration_local_verifier")


def _context() -> Any:
    adapter = _adapter()
    return adapter.AuthorizationAuditContext(
        campaign_id="campaign-079",
        run_id="run-079",
        step_id="step-079",
        attempt_id="attempt-079",
        principal="hermes-authorization",
        correlation_id="corr-079",
    )


def _event_kwargs() -> dict[str, object]:
    return {
        "event_type": "REGISTERED",
        "phase": "REGISTRATION",
        "decision": "ACCEPT",
        "reason_code": "RECEIPT_REGISTERED",
        "authorization_ref": "tb1-authz:v1:" + "a" * 64,
        "duplicate": False,
        "capability_id": "web.discovery.headers",
        "intrusiveness_level": "L1",
    }


def _enabled_custody() -> Any:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return custody.AuthorizationAuditCustody(policy)


def _new_custodied_adapter(tmp_path: Path) -> tuple[Any, Any]:
    adapter = _adapter()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "9" * 32,
        custody=_enabled_custody(),
        evidence_store=store,
        recorded_at_provider=lambda: "2026-08-16T05:10:00Z",
    )
    return instance, store


def test_custodied_event_binds_exact_evidence_id_into_audit_sink(tmp_path: Path) -> None:
    adapter = _adapter()
    instance, store = _new_custodied_adapter(tmp_path)

    record = instance.record_event(context=_context(), **_event_kwargs())
    digest, size = adapter.authorization_audit_record_digest(record)
    document = instance.seal(sealed_at="2026-08-16T05:11:00Z")
    entry = document["entries"][0]

    assert entry["object_ref"] == f"evidence://authorization-receipt-audit/{digest}"
    assert entry["object_digest_sha256"] == digest
    assert entry["object_size_bytes"] == size
    assert re.fullmatch(r"ev_[a-f0-9]{32}", entry["evidence_ref"])
    assert store.verify(entry["evidence_ref"]) is True


def test_custodied_event_verifies_through_existing_evidence_verifier_and_fails_on_tamper(
    tmp_path: Path,
) -> None:
    instance, store = _new_custodied_adapter(tmp_path)
    record = instance.record_event(context=_context(), **_event_kwargs())
    digest, _ = _adapter().authorization_audit_record_digest(record)

    verifier = _verifier_module().LocalEvidenceVerifier(store)
    resolver = _custody().EvidenceVerifierChainResolver(verifier)
    assert instance.verify(resolver=resolver)["verified"] is True

    evidence_id = instance.seal()["entries"][0]["evidence_ref"]
    evidence_record = store.get_record(evidence_id)
    object_digest = evidence_record["content"]["sha256"]
    assert object_digest == digest
    object_path = store.objects / object_digest[:2] / object_digest
    object_path.write_bytes(b"tampered")

    assert instance.verify(resolver=resolver)["verified"] is False


def test_exact_duplicate_creates_one_evidence_record_and_one_audit_entry(tmp_path: Path) -> None:
    instance, store = _new_custodied_adapter(tmp_path)
    first = instance.record_event(context=_context(), **_event_kwargs())
    second = instance.record_event(context=_context(), **_event_kwargs())

    assert second == first
    assert instance.length == 1
    assert len(list(store.records.glob("ev_*.json"))) == 1


def test_custody_failure_is_sanitized_and_creates_no_audit_entry() -> None:
    adapter = _adapter()

    class FailingCustody:
        def persist(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("/secret/path/token")

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "8" * 32,
        custody=FailingCustody(),
        evidence_store=object(),
        recorded_at_provider=lambda: "2026-08-16T05:10:00Z",
    )
    with pytest.raises(adapter.AuthorizationAuditError) as exc:
        instance.record_event(context=_context(), **_event_kwargs())

    assert exc.value.code == "AUTHORIZATION_AUDIT_CUSTODY_FAILED"
    assert "/secret/path/token" not in str(exc.value)
    assert instance.length == 0


@pytest.mark.parametrize(
    ("digest_delta", "size_delta", "ref"),
    [
        ("0" * 64, 0, "evidence://ev_" + "1" * 32),
        (None, 1, "evidence://ev_" + "1" * 32),
        (None, 0, "evidence://EV_" + "1" * 32),
    ],
)
def test_custody_identity_or_reference_mismatch_fails_before_audit_append(
    digest_delta: str | None,
    size_delta: int,
    ref: str,
) -> None:
    adapter = _adapter()

    class FakeCustody:
        def persist(self, record: dict[str, object], **_kwargs: object) -> object:
            digest, size = adapter.authorization_audit_record_digest(record)
            return SimpleNamespace(
                evidence_id="ev_" + "1" * 32,
                evidence_ref=ref,
                payload_sha256=digest_delta or digest,
                payload_size_bytes=size + size_delta,
                classification="restricted",
            )

    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "7" * 32,
        custody=FakeCustody(),
        evidence_store=object(),
        recorded_at_provider=lambda: "2026-08-16T05:10:00Z",
    )
    with pytest.raises(adapter.AuthorizationAuditError):
        instance.record_event(context=_context(), **_event_kwargs())
    assert instance.length == 0


def test_custody_correlation_is_derived_only_from_trusted_context() -> None:
    adapter = _adapter()
    captured: dict[str, object] = {}

    class RecordingCustody:
        def persist(
            self,
            record: dict[str, object],
            *,
            correlation: dict[str, str],
            recorded_at: str,
            evidence_store: object,
        ) -> object:
            captured["record"] = dict(record)
            captured["correlation"] = dict(correlation)
            captured["recorded_at"] = recorded_at
            captured["store"] = evidence_store
            digest, size = adapter.authorization_audit_record_digest(record)
            return SimpleNamespace(
                evidence_id="ev_" + "2" * 32,
                evidence_ref="evidence://ev_" + "2" * 32,
                payload_sha256=digest,
                payload_size_bytes=size,
                classification="restricted",
            )

    store = object()
    instance = adapter.CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "6" * 32,
        custody=RecordingCustody(),
        evidence_store=store,
        recorded_at_provider=lambda: "2026-08-16T05:10:00Z",
    )
    instance.record_event(context=_context(), **_event_kwargs())

    assert captured["correlation"] == {
        "campaign_id": "campaign-079",
        "run_id": "run-079",
        "step_id": "step-079",
        "attempt_id": "attempt-079",
    }
    assert captured["recorded_at"] == "2026-08-16T05:10:00Z"
    assert captured["store"] is store
    assert set(captured["record"]) == {
        "schema_version",
        "event_type",
        "phase",
        "decision",
        "reason_code",
        "authorization_ref_sha256",
        "duplicate",
        "capability_id",
        "intrusiveness_level",
        "promotion_allowed",
        "runtime_status",
        "execution_authority",
    }


def test_legacy_no_custody_path_remains_source_compatible() -> None:
    adapter = _adapter()
    instance = adapter.CanonicalAuthorizationAuditAdapter(chain_id="chain_" + "5" * 32)
    record = instance.record_event(context=_context(), **_event_kwargs())
    digest, size = adapter.authorization_audit_record_digest(record)
    entry = instance.seal(sealed_at="2026-08-16T05:11:00Z")["entries"][0]

    assert entry["object_ref"] == f"evidence://authorization-receipt-audit/{digest}"
    assert entry["object_digest_sha256"] == digest
    assert entry["object_size_bytes"] == size
    assert entry["evidence_ref"] is None
    assert instance.length == 1
