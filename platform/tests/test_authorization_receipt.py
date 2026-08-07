"""Adversarial tests for the TB1 control-plane authorization receipt.

Covers the contract/verifier itself (`platform/roe-contract/authorization_receipt.py`)
and its consumption at the gateway handoff boundary.

Every signing key is generated in memory. The repository stores no private key
material, no private key value is written to a repository path, and no private
key or signature value is printed. Nothing here executes a runner, a target, a
laboratory, a scanner, a network call or a subprocess.
"""

from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import authorization_receipt_fixtures as fixtures
from test_gateway_runner_handoff import (
    _admission_request,
    _contract,
    _issue,
    _kill_switch,
    _receipt_body,
    _sign,
    _step_request,
    _trust_store,
    handoff,
)

receipt_contract = fixtures.authorization_receipt
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "platform/roe-contract"


@pytest.fixture()
def scenario(tmp_path: Path) -> dict[str, Any]:
    """Admitted-and-authorized baseline: valid signed RoE plus valid receipt."""

    store, private_key = _trust_store(tmp_path)
    contract = _sign(_contract(), private_key)
    request = _admission_request(contract)
    step_request = _step_request()
    authorization_key = fixtures.new_key()
    authorization_store = fixtures.authorization_trust_store(
        tmp_path / "authorization-trust-store.json", authorization_key
    )
    return {
        "tmp_path": tmp_path,
        "private_key": private_key,
        "authorization_key": authorization_key,
        "contract": contract,
        "step_request": step_request,
        "request": request,
        "receipt": _issue(request, contract, step_request, authorization_key),
        "config": handoff.RunnerHandoffConfig(
            trust_store_path=store,
            kill_switch_path=_kill_switch(tmp_path),
            authorization_trust_store_path=authorization_store,
        ),
    }


def _call(scenario: dict[str, Any], **overrides: Any) -> Any:
    return handoff.build_step_request(
        overrides.get("request", scenario["request"]),
        overrides.get("contract", scenario["contract"]),
        overrides.get("step_request", scenario["step_request"]),
        overrides.get("config", scenario["config"]),
        authorization_receipt_document=(
            scenario["receipt"] if "receipt" not in overrides else overrides["receipt"]
        ),
    )


def _config(scenario: dict[str, Any], **overrides: Any) -> Any:
    base = scenario["config"]
    return handoff.RunnerHandoffConfig(
        trust_store_path=overrides.get("trust_store_path", base.trust_store_path),
        kill_switch_path=overrides.get("kill_switch_path", base.kill_switch_path),
        authorization_trust_store_path=overrides.get(
            "authorization_trust_store_path", base.authorization_trust_store_path
        ),
    )


# --------------------------------------------------------------------------
# positive path
# --------------------------------------------------------------------------


def test_valid_receipt_and_valid_roe_build_the_request(scenario) -> None:
    result = _call(scenario)

    assert result.request_built is True
    assert result.codes == ("HANDOFF_STEP_REQUEST_BUILT",)
    assert result.authorization_ref == scenario["receipt"]["authorization_ref"]


def test_ecdsa_p256_receipt_is_accepted(scenario, tmp_path: Path) -> None:
    key = fixtures.new_key("ECDSA-P256-SHA256")
    store = fixtures.authorization_trust_store(
        tmp_path / "p256-store.json",
        key,
        key_id=fixtures.AUTHORIZATION_KEY_ID_P256,
        algorithm="ECDSA-P256-SHA256",
    )
    receipt = fixtures.issue_receipt(
        _receipt_body(scenario["request"], scenario["contract"], scenario["step_request"]),
        key,
        key_id=fixtures.AUTHORIZATION_KEY_ID_P256,
        algorithm="ECDSA-P256-SHA256",
    )

    result = _call(
        scenario,
        receipt=receipt,
        config=_config(scenario, authorization_trust_store_path=store),
    )

    assert result.request_built is True
    assert result.authorization_ref == receipt["authorization_ref"]


# --------------------------------------------------------------------------
# missing / naked / forged authorization
# --------------------------------------------------------------------------


def test_missing_receipt_refuses(scenario) -> None:
    result = handoff.build_step_request(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        scenario["config"],
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_RECEIPT_REQUIRED",)


def test_missing_authorization_trust_store_config_refuses(scenario) -> None:
    result = _call(
        scenario, config=_config(scenario, authorization_trust_store_path=None)
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_TRUST_STORE_REQUIRED",)


@pytest.mark.parametrize(
    "field", ["authorization_ref", "authorization_receipt", "authorization"]
)
def test_naked_authorization_in_the_typed_request_refuses(scenario, field) -> None:
    request = copy.deepcopy(scenario["request"])
    request[field] = scenario["receipt"]["authorization_ref"]

    result = _call(scenario, request=request)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",)


def test_forged_authorization_ref_on_a_signed_receipt_refuses(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    receipt["authorization_ref"] = (
        receipt_contract.AUTHORIZATION_REF_PREFIX + "f" * 64
    )

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_REF_MISMATCH",)


def test_forged_receipt_body_after_signing_refuses(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    receipt["authorization"]["intrusiveness_level"] = "L4"

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_REF_MISMATCH",)


def test_forged_body_with_recomputed_ref_still_fails_the_signature(scenario) -> None:
    body = copy.deepcopy(scenario["receipt"])
    body.pop("signature")
    body.pop("authorization_ref")
    body["authorization"]["intrusiveness_level"] = "L4"
    body["authorization_ref"] = receipt_contract.compute_authorization_ref(body)
    forged = dict(body, signature=copy.deepcopy(scenario["receipt"]["signature"]))
    forged["signature"]["payload_sha256"] = receipt_contract.payload_sha256(forged)

    result = _call(scenario, receipt=forged)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_SIGNATURE_INVALID",)


def test_receipt_signed_by_an_unknown_key_refuses(scenario) -> None:
    other = fixtures.new_key()
    receipt = fixtures.issue_receipt(
        _receipt_body(scenario["request"], scenario["contract"], scenario["step_request"]),
        other,
        key_id="attacker-key",
    )

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_KEY_UNKNOWN",)


def test_receipt_signed_by_a_known_key_id_but_wrong_private_key_refuses(
    scenario,
) -> None:
    other = fixtures.new_key()
    receipt = fixtures.issue_receipt(
        _receipt_body(scenario["request"], scenario["contract"], scenario["step_request"]),
        other,
    )

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_SIGNATURE_INVALID",)


def test_tampered_signature_value_refuses(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    raw = bytearray(base64.b64decode(receipt["signature"]["value"]))
    raw[0] ^= 0xFF
    receipt["signature"]["value"] = base64.b64encode(bytes(raw)).decode("ascii")

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_SIGNATURE_INVALID",)


# --------------------------------------------------------------------------
# key purpose / cross-protocol key confusion
# --------------------------------------------------------------------------


def test_roe_purpose_key_cannot_authorize_tb1(scenario, tmp_path: Path) -> None:
    """A valid signing key bound to the RoE purpose must never authorize TB1."""

    key = fixtures.new_key()
    store = fixtures.authorization_trust_store(
        tmp_path / "roe-purpose-store.json", key, purpose="roe-contract-signing"
    )
    receipt = fixtures.issue_receipt(
        _receipt_body(scenario["request"], scenario["contract"], scenario["step_request"]),
        key,
    )

    result = _call(
        scenario,
        receipt=receipt,
        config=_config(scenario, authorization_trust_store_path=store),
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_KEY_PURPOSE_MISMATCH",)


def test_document_level_purpose_mismatch_refuses(scenario, tmp_path: Path) -> None:
    key = fixtures.new_key()
    store = fixtures.authorization_trust_store(
        tmp_path / "mixed-purpose-store.json",
        key,
        document_purpose="roe-contract-signing",
    )
    receipt = fixtures.issue_receipt(
        _receipt_body(scenario["request"], scenario["contract"], scenario["step_request"]),
        key,
    )

    result = _call(
        scenario,
        receipt=receipt,
        config=_config(scenario, authorization_trust_store_path=store),
    )

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_KEY_PURPOSE_MISMATCH",)


def test_pointing_at_the_roe_trust_store_refuses(scenario) -> None:
    """The RoE signing trust store is structurally rejected for authorization."""

    result = _call(
        scenario,
        config=_config(
            scenario,
            authorization_trust_store_path=scenario["config"].trust_store_path,
        ),
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_KEY_PURPOSE_MISMATCH",)


def test_domain_separation_blocks_cross_protocol_replay(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    preimage = receipt_contract.canonical_reference_preimage(
        {k: v for k, v in receipt.items() if k != "signature"}
    )

    assert preimage.startswith(receipt_contract.AUTHORIZATION_DOMAIN.encode("utf-8"))
    assert receipt_contract.AUTHORIZATION_DOMAIN == "hex0r.tb1.authorization.v1"


def test_wrong_domain_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"], scenario["contract"], scenario["step_request"]
    )
    body["domain"] = "hex0r.roe.contract.v1"
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_RECEIPT_SCHEMA_INVALID",)


def test_non_control_plane_issuer_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"], scenario["contract"], scenario["step_request"]
    )
    body["issuer"]["plane"] = "execution-plane"
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_RECEIPT_SCHEMA_INVALID",)


# --------------------------------------------------------------------------
# key state and validity
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state, code",
    [
        ("revoked", "AUTHORIZATION_KEY_REVOKED"),
        ("retired", "AUTHORIZATION_KEY_NOT_ACTIVE"),
    ],
)
def test_non_active_authorization_key_refuses(
    scenario, tmp_path: Path, state, code
) -> None:
    store = fixtures.authorization_trust_store(
        tmp_path / f"{state}-store.json", scenario["authorization_key"], state=state
    )

    result = _call(
        scenario, config=_config(scenario, authorization_trust_store_path=store)
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == (code,)


@pytest.mark.parametrize(
    "window, code",
    [
        (
            {"not_after": "2001-01-01T00:00:00Z", "not_before": "2000-01-01T00:00:00Z"},
            "AUTHORIZATION_KEY_EXPIRED",
        ),
        (
            {"not_before": "2099-01-01T00:00:00Z", "not_after": "2100-01-01T00:00:00Z"},
            "AUTHORIZATION_KEY_NOT_YET_VALID",
        ),
    ],
)
def test_authorization_key_outside_its_window_refuses(
    scenario, tmp_path: Path, window, code
) -> None:
    store = fixtures.authorization_trust_store(
        tmp_path / "window-store.json", scenario["authorization_key"], **window
    )

    result = _call(
        scenario, config=_config(scenario, authorization_trust_store_path=store)
    )

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == (code,)


def test_malformed_authorization_trust_store_refuses(
    scenario, tmp_path: Path
) -> None:
    store = tmp_path / "broken-store.json"
    store.write_text("{ not json", encoding="utf-8")

    result = _call(
        scenario, config=_config(scenario, authorization_trust_store_path=store)
    )

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_TRUST_STORE_INVALID",)


def test_absent_authorization_trust_store_refuses(scenario, tmp_path: Path) -> None:
    result = _call(
        scenario,
        config=_config(
            scenario, authorization_trust_store_path=tmp_path / "absent-store.json"
        ),
    )

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_TRUST_STORE_UNAVAILABLE",)


def test_trust_store_carrying_private_material_refuses(
    scenario, tmp_path: Path
) -> None:
    store = tmp_path / "secret-store.json"
    document = json.loads(
        scenario["config"].authorization_trust_store_path.read_text(encoding="utf-8")
    )
    document["keys"][0]["private_key"] = "REDACTED-NOT-A-REAL-KEY"
    store.write_text(json.dumps(document), encoding="utf-8")

    result = _call(
        scenario, config=_config(scenario, authorization_trust_store_path=store)
    )

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_TRUST_STORE_SECRET_MATERIAL",)


# --------------------------------------------------------------------------
# receipt validity window
# --------------------------------------------------------------------------


def _offset_stamp(seconds: int) -> str:
    moment = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        seconds=seconds
    )
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_expired_receipt_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        issued_at=_offset_stamp(-3000),
        expires_at=_offset_stamp(-1200),
    )
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTHORIZATION_RECEIPT_EXPIRED",)


def test_not_yet_valid_receipt_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        issued_at=_offset_stamp(1200),
        expires_at=_offset_stamp(2400),
    )
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_RECEIPT_NOT_YET_VALID",)


def test_inverted_validity_window_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        issued_at=_offset_stamp(600),
        expires_at=_offset_stamp(-600),
    )
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_RECEIPT_WINDOW_INVALID",)


def test_over_long_validity_window_refuses(scenario) -> None:
    body = _receipt_body(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        issued_at=_offset_stamp(-60),
        expires_at=_offset_stamp(60 + receipt_contract.MAX_VALIDITY_SECONDS + 60),
    )
    receipt = fixtures.issue_receipt(body, scenario["authorization_key"])

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_RECEIPT_WINDOW_TOO_LONG",)


# --------------------------------------------------------------------------
# binding cross-checks against the freshly admitted context
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override, code",
    [
        ({"campaign_id": "8f9e0a1b-2c3d-4e5f-9a8b-7c6d5e4f3a2b"}, "AUTHORIZATION_CAMPAIGN_MISMATCH"),
        ({"run_id": "2e5a7b93-6f84-4d3a-8b19-7c9d1e3f5a68"}, "AUTHORIZATION_RUN_MISMATCH"),
        ({"step_id": "4c7e9a15-3b62-4d80-9e21-8f0a2c4e6b93"}, "AUTHORIZATION_STEP_MISMATCH"),
        ({"roe_contract_id": "roe-contract-other"}, "AUTHORIZATION_ROE_CONTRACT_MISMATCH"),
        (
            {"roe_contract_payload_sha256": "0" * 64},
            "AUTHORIZATION_ROE_CONTRACT_PAYLOAD_MISMATCH",
        ),
        (
            {"roe_step_request_id": "roe-step-request-other"},
            "AUTHORIZATION_ROE_STEP_REQUEST_MISMATCH",
        ),
        ({"operation_id": "web.discovery.tls"}, "AUTHORIZATION_OPERATION_MISMATCH"),
        ({"operation_version": "2.0.0"}, "AUTHORIZATION_OPERATION_VERSION_MISMATCH"),
        ({"capability_id": "web.discovery.tls"}, "AUTHORIZATION_CAPABILITY_MISMATCH"),
        ({"target_sha256": "a" * 64}, "AUTHORIZATION_TARGET_MISMATCH"),
        ({"intrusiveness_level": "L2"}, "AUTHORIZATION_INTRUSIVENESS_MISMATCH"),
    ],
)
def test_binding_divergence_refuses_with_a_stable_code(
    scenario, override, code
) -> None:
    receipt = _issue(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        scenario["authorization_key"],
        **override,
    )

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.runner_request is None
    assert code in result.codes


def test_receipt_for_another_step_cannot_authorize_this_one(scenario) -> None:
    other_request = copy.deepcopy(scenario["request"])
    other_request["step_id"] = "4c7e9a15-3b62-4d80-9e21-8f0a2c4e6b93"
    receipt = _issue(
        other_request,
        scenario["contract"],
        scenario["step_request"],
        scenario["authorization_key"],
    )

    result = _call(scenario, receipt=receipt)

    assert result.request_built is False
    assert result.codes == ("AUTHORIZATION_STEP_MISMATCH",)


# --------------------------------------------------------------------------
# no refusal ever yields a runner request; no leakage anywhere
# --------------------------------------------------------------------------


def test_no_refusal_path_ever_produces_a_runner_request(scenario, tmp_path: Path) -> None:
    refusals = [
        handoff.build_step_request(
            scenario["request"],
            scenario["contract"],
            scenario["step_request"],
            scenario["config"],
        ),
        _call(scenario, config=_config(scenario, authorization_trust_store_path=None)),
        _call(
            scenario,
            config=_config(
                scenario,
                authorization_trust_store_path=tmp_path / "absent-store.json",
            ),
        ),
        _call(scenario, receipt={"schema_version": "1.0.0"}),
        _call(
            scenario,
            receipt=_issue(
                scenario["request"],
                scenario["contract"],
                scenario["step_request"],
                fixtures.new_key(),
            ),
        ),
    ]

    for result in refusals:
        assert result.request_built is False
        assert result.runner_request is None
        assert result.authorization_ref is None
        assert result.idempotency_key is None
        assert result.request_fingerprint is None
        assert result.codes


def test_refusal_metadata_leaks_no_receipt_or_store_material(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    receipt["authorization"]["target_sha256"] = "b" * 64
    receipt = fixtures.issue_receipt(
        {k: v for k, v in receipt.items() if k not in {"signature", "authorization_ref"}},
        scenario["authorization_key"],
    )

    result = _call(scenario, receipt=receipt)
    rendered = repr(result)
    serialized = json.dumps(result.sanitized_summary())

    for blob in (rendered, serialized):
        assert "juice-shop-demo" not in blob
        assert receipt["signature"]["value"] not in blob
        assert str(scenario["config"].authorization_trust_store_path) not in blob
        assert str(scenario["config"].trust_store_path) not in blob
        for forbidden in ("private_key", "public_key", "passphrase", "seed"):
            assert forbidden not in blob


def test_verified_authorization_projection_carries_no_payload(scenario) -> None:
    verified = receipt_contract.verify_receipt(
        scenario["receipt"], scenario["config"].authorization_trust_store_path
    )
    rendered = repr(verified)

    assert "juice-shop-demo" not in rendered
    assert scenario["receipt"]["signature"]["value"] not in rendered
    for forbidden in ("private_key", "public_key", "signature", "passphrase"):
        assert forbidden not in rendered


# --------------------------------------------------------------------------
# repository hygiene: no issuer, no private key material
# --------------------------------------------------------------------------


def test_repository_ships_no_private_key_material() -> None:
    markers = (
        "BEGIN PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
    )
    for path in CONTRACT_DIR.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            assert marker not in text, f"{path} contains private key material"


def test_contract_module_implements_no_operational_issuer() -> None:
    source = (CONTRACT_DIR / "authorization_receipt.py").read_text(encoding="utf-8")

    assert "def sign_receipt" not in source
    assert "def issue_receipt" not in source
    for forbidden in (
        "load_pem_private_key",
        "load_der_private_key",
        "private_bytes",
        "Ed25519PrivateKey",
        "generate_private_key",
    ):
        assert forbidden not in source, f"{forbidden} would make this an issuer"
    assert "NOT_IMPLEMENTED" in source
    assert "NOT_RUN" in source
