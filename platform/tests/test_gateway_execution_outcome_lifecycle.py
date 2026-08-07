from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPIC = ROOT / "docs/roadmap/epics/EPIC-03-typed-kali-mcp.md"
README = ROOT / "platform/gateway-protocol/README.md"
CONTRACTS = ROOT / "docs/architecture/contracts/README.md"
SCHEMA = ROOT / "platform/gateway-protocol/gateway-execution-outcome.schema.json"
OUTCOME = ROOT / "platform/gateway-protocol/outcome.py"


def test_gateway_readme_declares_sanitized_outcome_without_runtime_claim() -> None:
    text = README.read_text(encoding="utf-8")

    assert "typed execution outcome schema/derivation: `CANDIDATE`" in text
    assert "real runner identity/transport authentication: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "deployed gateway outcome reception: `NOT_RUN`" in text
    assert "Evidence Plane outcome persistence: `NOT_RUN`" in text
    assert "raw Runner `output`" in text
    assert "evidence `uri`" in text
    assert "error `message` and `safe_context`" in text
    assert "does not prove that a real runner actually executed" in text


def test_epic_remains_implementing_and_non_final_after_outcome_candidate() -> None:
    text = EPIC.read_text(encoding="utf-8")

    assert "**IMPLEMENTING**" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "sanitized typed execution outcome derivation: `CANDIDATE`" in text
    assert "real runner identity/transport authentication: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "real Runner Protocol dispatch/capability execution: `NOT_RUN`" in text
    assert "Evidence Plane runtime integration: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_contract_inventory_promotes_only_tb1_outcome_not_evidence_plane() -> None:
    text = CONTRACTS.read_text(encoding="utf-8")

    row = next(
        line for line in text.splitlines() if line.startswith("| Typed execution outcome |")
    )
    assert "`IMPLEMENTING`" in row
    assert "real runner identity/transport authentication" in row
    assert "`NOT_IMPLEMENTED` / `NOT_RUN`" in row
    evidence_row = next(
        line for line in text.splitlines() if line.startswith("| Evidence write envelope |")
    )
    assert "`INTENT`" in evidence_row


def test_outcome_schema_cannot_transport_raw_runner_payload_fields() -> None:
    text = SCHEMA.read_text(encoding="utf-8")

    assert '"additionalProperties": false' in text
    assert '"output_present"' in text
    assert '"request_envelope_sha256"' in text
    assert '"authorization_ref"' in text
    assert '"output":' not in text
    assert '"uri":' not in text
    assert '"message":' not in text
    assert '"safe_context":' not in text
    assert '"authorization_receipt":' not in text


def test_outcome_code_preserves_non_authorizing_non_runtime_boundary() -> None:
    text = OUTCOME.read_text(encoding="utf-8")

    assert "never treats an outcome as authorization" in text
    assert "Runner identity" in text
    assert "NOT_IMPLEMENTED / NOT_RUN" in text
    assert "sealed_request_json" in text
    assert "request_envelope_sha256" in text
    assert '"uri"' not in text.split("def _sanitize_outcome", 1)[1].split("def _validate_gateway_outcome", 1)[0]
    assert '"message"' not in text.split("def _sanitize_outcome", 1)[1].split("def _validate_gateway_outcome", 1)[0]
    assert '"safe_context"' not in text.split("def _sanitize_outcome", 1)[1].split("def _validate_gateway_outcome", 1)[0]
