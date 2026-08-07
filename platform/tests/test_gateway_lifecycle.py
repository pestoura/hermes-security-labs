from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INTENT = ROOT / "docs/roadmap/epics/EPIC-03-typed-kali-mcp.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-03-typed-gateway-contract-candidate-as-built.md"
README = ROOT / "platform/gateway-protocol/README.md"
RUNNER_README = ROOT / "platform/runner-protocol/README.md"
REGISTRY = ROOT / "platform/gateway-protocol/operation-registry.yaml"


def test_concept_epic_remains_intent_with_reserved_lifecycle_sections() -> None:
    text = INTENT.read_text(encoding="utf-8")

    assert "**INTENT**" in text
    tail = text.split("## 14. Implementation notes", 1)[1]
    assert "Reserved" in tail
    assert "| FINAL | no |" in text


def test_supplementary_record_never_claims_deployment_or_final() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    assert "AS_BUILT — contract candidate" in text
    assert "| FINAL | no |" in text
    assert "Kali MCP handler integration: `NOT_RUN`" in text
    assert "gateway deployment: `NOT_RUN`" in text
    assert "production runtime observation: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_supplementary_record_references_every_gateway_component() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    for path in (
        "operation-registry.schema.json",
        "gateway-request.schema.json",
        "operation-registry.yaml",
        "gateway_protocol.py",
        "test_gateway_protocol.py",
        "platform/registry.yaml",
    ):
        assert path in text


def test_gateway_readme_preserves_unimplemented_runtime_boundaries() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Kali MCP handler integration: `NOT_RUN`" in text
    assert "gateway deployment: `NOT_RUN`" in text
    assert "production runtime observation: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_gateway_readme_declares_the_handoff_as_non_runtime() -> None:
    text = README.read_text(encoding="utf-8")

    assert "canonical gateway -> Runner Protocol v2 handoff: `CANDIDATE`" in text
    assert "runtime authorization-ref resolution: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "runner execution integration: `execution_integration: NOT_RUN`" in text
    assert "`NO_RUNTIME_CHANGE`" in text


def test_gateway_readme_does_not_call_message_construction_a_dispatch() -> None:
    text = README.read_text(encoding="utf-8")

    assert "`request_built`, not `dispatched`" in text
    assert "RESTRICTED operational payload" in text
    assert "`attempt_id` is\n  deliberately excluded" in text


def test_runner_protocol_readme_declares_the_handoff_as_reference_only() -> None:
    text = RUNNER_README.read_text(encoding="utf-8")

    assert "a bearer token, grant, capability or" in text
    assert "`NOT_IMPLEMENTED` and `NOT_RUN`" in text
    assert "`execution_integration: NOT_RUN`" in text


def test_normal_profile_inventory_remains_explicit_and_non_intrusive() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    operations = {item["id"]: item for item in registry["operations"]}
    normal = registry["profiles"]["normal"]

    assert normal["generic_execution"] is False
    assert set(normal["operations"]) == {
        "system.health.read",
        "runtime.inventory.read",
        "web.discovery.headers",
        "web.discovery.tls",
    }
    assert all(operations[item]["intrusiveness_level"] in {"L0", "L1"} for item in normal["operations"])
    assert all(item["production_status"] == "NOT_RUN" for item in operations.values())
