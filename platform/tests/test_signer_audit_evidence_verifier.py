from __future__ import annotations

import ast
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
EVIDENCE = ROOT / "platform" / "evidence-plane"
CUSTODY_PATH = EVIDENCE / "signer_audit_custody.py"
POLICY_PATH = EVIDENCE / "signer-audit-custody-policy.yaml"
ADAPTER_PATH = ASSURANCE / "signer_audit_adapter.py"
SIGNING_PATH = ASSURANCE / "signing_service.py"
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


def _signing():
    return _load(SIGNING_PATH, "chg_hsl_076_signing")


def _adapter():
    return _load(ADAPTER_PATH, "chg_hsl_076_signer_audit_adapter")


def _custody():
    return _load(CUSTODY_PATH, "chg_hsl_076_signer_audit_custody")


def _store_module():
    return _load(STORE_PATH, "chg_hsl_076_local_store")


def _verifier_module():
    return _load(VERIFIER_PATH, "chg_hsl_076_local_verifier")


def _request():
    signing = _signing()
    return signing.SigningRequest(
        digest_sha256="a" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-076",
    )


def _result():
    signing = _signing()
    return signing.SigningResult(
        signature_b64="YQ==",
        key_id="key-076",
        algorithm="Ed25519",
        public_key_spki_sha256="b" * 64,
        signer_class="VAULT",
        authority="EXTERNAL_CUSTODY",
        admissible_for_lab_l1=True,
        audit_ref="evidence://signer/provider-audit-076",
    )


def _attribution():
    adapter = _adapter()
    return adapter.SignerAuditAttribution(
        principal="hermes-assurance",
        provider_ref="provider-ref-076",
        test_only=False,
    )


def _event() -> dict[str, object]:
    return _adapter().build_signer_audit_record(_request(), _result(), _attribution())


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-076",
        "run_id": "run-076",
        "step_id": "sign-076",
        "attempt_id": "attempt-076",
    }


def _enabled_policy() -> dict[str, Any]:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    policy["state"] = "ENABLED"
    return policy


def test_canonical_policy_is_disabled_and_fail_closed() -> None:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["custody"]["classification"] == "restricted"
    assert policy["custody"]["include_original_signing_payload"] is False
    assert policy["custody"]["include_raw_signature"] is False
    assert custody.validate_policy(policy) == []

    bridge = custody.SignerAuditCustody(policy)
    with pytest.raises(custody.SignerAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T00:30:00Z",
            evidence_store=object(),
        )
    assert exc.value.code == "CUSTODY_DISABLED"


def test_enabled_test_policy_projects_exact_public_event_to_existing_store(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = _event()
    result = custody.SignerAuditCustody(_enabled_policy()).persist(
        event,
        correlation=_correlation(),
        recorded_at="2026-08-16T00:30:00Z",
        evidence_store=store,
    )

    assert store.verify(result.evidence_id) is True
    assert result.evidence_ref == f"evidence://{result.evidence_id}"
    assert result.classification == "restricted"
    assert result.payload_sha256 == _adapter().signer_record_digest(event)[0]

    record = store.get_record(result.evidence_id)
    assert record["classification"] == "restricted"
    assert record["correlation"] == _correlation()
    assert record["origin"]["producer"] == "signer-operation-audit-custody-v1"
    assert record["origin"]["operation"] == "signer.audit.SIGN"
    assert record["content"]["sha256"] == result.payload_sha256
    assert record["content"]["storage_ref"] == (
        f"evidence://signer-operation/{result.payload_sha256}"
    )
    assert record["retention"]["policy_id"] == "default-30d"

    digest = record["content"]["sha256"]
    payload = (store.objects / digest[:2] / digest).read_text(encoding="utf-8")
    decoded = json.loads(payload)
    assert decoded == event
    for forbidden in (
        "signature_b64",
        "payload",
        "private_key",
        "secret",
        "token",
        "credential",
    ):
        assert forbidden not in payload


def test_identical_persistence_is_idempotent_in_canonical_store(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    bridge = custody.SignerAuditCustody(_enabled_policy())
    kwargs = {
        "correlation": _correlation(),
        "recorded_at": "2026-08-16T00:30:00Z",
        "evidence_store": store,
    }
    first = bridge.persist(_event(), **kwargs)
    second = bridge.persist(_event(), **kwargs)
    assert second.evidence_id == first.evidence_id
    assert second.payload_sha256 == first.payload_sha256
    assert len(list(store.records.glob("ev_*.json"))) == 1


def test_local_evidence_verifier_binds_exact_ref_digest_and_storage_ref(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    result = custody.SignerAuditCustody(_enabled_policy()).persist(
        _event(),
        correlation=_correlation(),
        recorded_at="2026-08-16T00:30:00Z",
        evidence_store=store,
    )
    verifier = _verifier_module().LocalEvidenceVerifier(store)
    record = store.get_record(result.evidence_id)
    storage_ref = record["content"]["storage_ref"]

    assert verifier.verify(result.evidence_ref, result.payload_sha256) is True
    assert verifier.verify(result.evidence_id, result.payload_sha256) is True
    assert verifier.verify(storage_ref, result.payload_sha256) is True
    assert verifier.verify(result.evidence_ref, "0" * 64) is False
    assert verifier.verify("evidence://ev_" + "f" * 32, result.payload_sha256) is False

    digest = record["content"]["sha256"]
    object_path = store.objects / digest[:2] / digest
    object_path.write_bytes(b"tampered")
    assert verifier.verify(result.evidence_ref, result.payload_sha256) is False
    assert verifier.verify(storage_ref, result.payload_sha256) is False


def test_audit_sink_can_bind_and_verify_custodied_signer_event(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    request = _request()
    result = _result()
    attribution = _attribution()
    event = _adapter().build_signer_audit_record(request, result, attribution)
    persisted = custody.SignerAuditCustody(_enabled_policy()).persist(
        event,
        correlation=_correlation(),
        recorded_at="2026-08-16T00:30:00Z",
        evidence_store=store,
    )
    verifier = _verifier_module().LocalEvidenceVerifier(store)
    resolver = custody.EvidenceVerifierChainResolver(verifier)

    sink = _adapter().CanonicalSignerAuditAdapter(
        chain_id="chain_" + "7" * 32,
        correlation=_correlation(),
    )
    returned = sink.record_signing(
        request=request,
        result=result,
        attribution=attribution,
        evidence_ref=persisted.evidence_ref,
    )
    assert returned == event
    document = sink.seal(sealed_at="2026-08-16T00:31:00Z")
    assert document["entries"][0]["evidence_ref"] == persisted.evidence_id
    assert document["entries"][0]["object_ref"] == (
        f"evidence://signer-operation/{persisted.payload_sha256}"
    )
    verified = sink.verify(resolver=resolver)
    assert verified["verified"] is True


def test_chain_resolver_is_only_an_interface_adapter_and_fails_closed() -> None:
    custody = _custody()

    class Verifier:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def verify(self, evidence_ref: str, sha256: str) -> bool:
            self.calls.append((evidence_ref, sha256))
            return True

    verifier = Verifier()
    resolver = custody.EvidenceVerifierChainResolver(verifier)
    digest = "a" * 64
    assert resolver(
        object_ref="evidence://signer-operation/" + digest,
        object_digest_sha256=digest,
        object_size_bytes=42,
    ) is True
    assert verifier.calls == [("evidence://signer-operation/" + digest, digest)]
    assert resolver(
        object_ref="",
        object_digest_sha256=digest,
        object_size_bytes=42,
    ) is False


def test_invalid_or_secret_bearing_event_is_refused_before_write(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = deepcopy(_event())
    event["token"] = "forbidden"
    with pytest.raises(custody.SignerAuditCustodyError) as exc:
        custody.SignerAuditCustody(_enabled_policy()).persist(
            event,
            correlation=_correlation(),
            recorded_at="2026-08-16T00:30:00Z",
            evidence_store=store,
        )
    assert exc.value.code == "SIGNER_AUDIT_EVENT_INVALID"
    assert list(store.records.glob("*.json")) == []


def test_store_contract_and_backend_failures_fail_closed_without_leakage() -> None:
    custody = _custody()
    bridge = custody.SignerAuditCustody(_enabled_policy())

    with pytest.raises(custody.SignerAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T00:30:00Z",
            evidence_store=None,
        )
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"

    class FailingStore:
        def put(self, record, payload):  # noqa: ANN001
            raise RuntimeError("/sensitive/backend/path")

        def verify(self, evidence_id):  # noqa: ANN001
            return True

    with pytest.raises(custody.SignerAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T00:30:00Z",
            evidence_store=FailingStore(),
        )
    assert exc.value.code == "EVIDENCE_PROJECTION_FAILED"
    assert "/sensitive/backend/path" not in str(exc.value)

    class NonVerifyingStore:
        def put(self, record, payload):  # noqa: ANN001
            return record["evidence_id"]

        def verify(self, evidence_id):  # noqa: ANN001
            return False

    with pytest.raises(custody.SignerAuditCustodyError) as exc:
        bridge.persist(
            _event(),
            correlation=_correlation(),
            recorded_at="2026-08-16T00:30:00Z",
            evidence_store=NonVerifyingStore(),
        )
    assert exc.value.code == "EVIDENCE_VERIFICATION_FAILED"


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda p: p.update(state="BROKEN"), "state must be DISABLED or ENABLED"),
        (lambda p: p.update(default="allow"), "default must be deny"),
        (lambda p: p.update(runtime_status="READY"), "runtime_status must remain NOT_RUN"),
        (lambda p: p.update(execution_authority="runner"), "must never claim execution authority"),
        (lambda p: p["custody"].update(classification="summary"), "classification must be restricted"),
        (lambda p: p["custody"].update(retention_days=0), "retention_days"),
        (lambda p: p["custody"].update(include_original_signing_payload=True), "original signing payload"),
        (lambda p: p["custody"].update(include_raw_signature=True), "raw signature"),
    ],
)
def test_policy_mutations_fail_validation(mutator, expected: str) -> None:  # noqa: ANN001
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    mutator(policy)
    assert any(expected in finding for finding in custody.validate_policy(policy))


def test_custody_source_has_no_parallel_store_chain_verifier_or_runtime_effect() -> None:
    _custody()
    source = CUSTODY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
    assert not imported & {
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "boto3",
        "hvac",
        "pkcs11",
        "docker",
    }
    assert "LocalEvidenceStore" not in called_names
    assert "EvidenceChain" not in called_names
    assert "LocalEvidenceVerifier" not in called_names
    assert "seal_chain" not in called_names
    assert "evidence_store.put(" in source
    assert "evidence_store.verify(" in source
