#!/usr/bin/env python3
"""Temporary exact patch for the EPIC-05 API conformance candidate block."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    start_at = text.index(start)
    end_at = text.index(end, start_at + len(start))
    file_path.write_text(text[:start_at] + replacement + text[end_at:], encoding="utf-8")


def replace_in_section(path: str, start: str, end: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    start_at = text.index(start)
    end_at = text.index(end, start_at + len(start))
    section = text[start_at:end_at]
    count = section.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: section {start.strip()!r} expected one occurrence, "
            f"found {count}: {old!r}"
        )
    section = section.replace(old, new, 1)
    file_path.write_text(text[:start_at] + section + text[end_at:], encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"{path}: marker expected once, found {count}: {marker!r}")
    file_path.write_text(text.replace(marker, content + marker, 1), encoding="utf-8")


def main() -> None:
    contracts_py = "platform/runner-protocol/src/runner_protocol_v2/contracts.py"
    replace_once(
        contracts_py,
        '    data = yaml.safe_load((root / "compatibility.yaml").read_text(encoding="utf-8"))\n'
        '    if data["protocol"] != {\n',
        '    data = yaml.safe_load((root / "compatibility.yaml").read_text(encoding="utf-8"))\n'
        '    if data.get("schema_version") != "1.1":\n'
        '        raise ProtocolValidationError("compatibility schema version must be 1.1")\n'
        '    if data["protocol"] != {\n',
    )
    family_section = '''    families = data["runner_families"]
    ids = {family["id"] for family in families}
    if ids != EXPECTED_RUNNER_FAMILIES:
        raise ProtocolValidationError(
            f"runner family inventory mismatch: {sorted(ids)}"
        )
    for family in families:
        if family["implementation_status"] != "not_started":
            raise ProtocolValidationError(
                f"{family['id']} cannot claim implementation before an adapter block"
            )
        if family["protocol_status"] != "contract_only":
            raise ProtocolValidationError(
                f"{family['id']} protocol status must remain contract_only"
            )
        if family["conformance"] != "NOT_RUN":
            raise ProtocolValidationError(
                f"{family['id']} conformance must remain NOT_RUN"
            )

    if data["runtime_declaration"] != "NO_RUNTIME_CHANGE":
        raise ProtocolValidationError("runtime declaration must be NO_RUNTIME_CHANGE")
'''
    new_family_section = '''    families = data["runner_families"]
    if not isinstance(families, list):
        raise ProtocolValidationError("runner family inventory must be a list")
    ids = [family.get("id") for family in families]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_RUNNER_FAMILIES:
        raise ProtocolValidationError(
            f"runner family inventory mismatch: {sorted(str(value) for value in ids)}"
        )
    by_id = {family["id"]: family for family in families}

    api_expected = {
        "implementation_status": "candidate",
        "protocol_status": "conformance_only",
        "conformance": "PASS_SYNTHETIC",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "supported_scope": "synthetic_conformance_only",
        "activation": "explicit_flag",
        "adapter_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "runner_protocol_adapter.py"
        ),
        "activation_argument": "--conformance-only",
    }
    api = by_id["api"]
    for key, expected in api_expected.items():
        if api.get(key) != expected:
            raise ProtocolValidationError(
                f"API candidate field {key!r} must be {expected!r}"
            )

    repository_root = root.parents[1]
    adapter_path = (repository_root / str(api["adapter_path"])).resolve()
    if repository_root not in adapter_path.parents or not adapter_path.is_file():
        raise ProtocolValidationError("API candidate path is missing or outside repository")
    adapter_source = adapter_path.read_text(encoding="utf-8")
    for forbidden in ("execute_runbook", "execute_command"):
        if forbidden in adapter_source:
            raise ProtocolValidationError(
                f"API conformance candidate must not reference {forbidden}"
            )
    if str(api["activation_argument"]) not in adapter_source:
        raise ProtocolValidationError("API candidate activation flag is not enforced")

    not_started_expected = {
        "implementation_status": "not_started",
        "protocol_status": "contract_only",
        "conformance": "NOT_RUN",
        "execution_integration": "NOT_RUN",
        "promotion_status": "blocked",
        "supported_scope": "none",
        "activation": "none",
        "adapter_path": None,
        "activation_argument": None,
    }
    for family_id in ("devsecops", "ai-mcp"):
        family = by_id[family_id]
        for key, expected in not_started_expected.items():
            if family.get(key) != expected:
                raise ProtocolValidationError(
                    f"{family_id} field {key!r} must remain {expected!r}"
                )

    if data["runtime_declaration"] != "NO_RUNTIME_CHANGE":
        raise ProtocolValidationError("runtime declaration must be NO_RUNTIME_CHANGE")
'''
    replace_once(contracts_py, family_section, new_family_section)

    protocol_tests = "platform/runner-protocol/tests/test_runner_protocol.py"
    replace_once(
        protocol_tests,
        "def test_compatibility_matrix_is_contract_only() -> None:\n",
        "def test_compatibility_matrix_accepts_scoped_api_candidate() -> None:\n",
    )

    protocol_readme = "platform/runner-protocol/README.md"
    replace_once(
        protocol_readme,
        "- Current implementation state: contract, repository-local SDK and vendor-neutral conformance kit available; no existing API, DevSecOps or AI/MCP runner is claimed conformant.\n",
        "- Current implementation state: contract, repository-local SDK and vendor-neutral conformance kit are available; an API-family candidate passes synthetic conformance only, while real execution integration for API, DevSecOps and AI/MCP remains unimplemented.\n",
    )
    insert_before(
        protocol_readme,
        "## Non-goals of this block\n",
        '''## API-family conformance candidate

The first family-specific candidate is implemented at
[`security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py`](../../security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py).
It is an opt-in protocol candidate, not a production runner.

The process starts only with `--conformance-only`, accepts only synthetic `conformance.*`
capabilities and the synthetic authorization reference `authz/conformance/active`, and uses an
in-memory ledger. It has no network, subprocess, file, bridge or legacy executor dependency.
Any real API capability, real authorization reference or unsupported control action fails closed.

The vendor-neutral conformance kit returns `PASS` for this candidate. The compatibility record
therefore uses the deliberately narrower state `PASS_SYNTHETIC`, while preserving:

- `execution_integration: NOT_RUN`;
- `promotion_status: blocked`;
- no connection to `execute_runbook()`;
- no connection to `ProcessBridgeAdapter` or `execute_command`;
- no persistent idempotency ledger;
- no live process cancellation or customer-target execution.

`PASS_SYNTHETIC` proves protocol behaviour only. It cannot be used as evidence of production
safety, operational readiness or real API-runner conformance.

''',
    )

    api_readme = "security/packs/api/README.md"
    insert_before(
        api_readme,
        "## Princípio operacional\n",
        '''## Runner Protocol v2 — candidato isolado

O pack inclui um candidato opt-in em
`src/api_pentest_runbooks/runner_protocol_adapter.py`, destinado exclusivamente ao conformance
kit do Runner Protocol v2.

Este candidato:

- só arranca com `--conformance-only`;
- aceita apenas capabilities sintéticas `conformance.*`;
- usa apenas estado em memória;
- não importa nem chama `execute_runbook`, `ProcessBridgeAdapter` ou `execute_command`;
- não executa rede, subprocessos, ficheiros ou ferramentas de segurança;
- recusa capabilities e referências de autorização reais;
- está desligado do caminho operacional descrito abaixo.

O resultado atual é `PASS_SYNTHETIC`, com integração de execução `NOT_RUN` e promoção bloqueada.
Não representa um runner API operacional nem altera o comportamento existente do pack.

''',
    )

    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.4.0 |", "| Document version | 1.4.1 |")
    replace_once(
        epic,
        "end-to-end conformance, idempotent effects or bounded live cancellation.\n",
        "end-to-end production conformance, durable idempotent effects or bounded live\n"
        "cancellation. An API-family candidate is now being implemented in synthetic-only, opt-in\n"
        "mode; this does not satisfy the remaining epic-level criteria.\n",
    )
    insert_before(
        epic,
        "## 15. As-built / final architecture\n",
        '''### Block 4 — API-family conformance candidate (`IMPLEMENTING`)

- Branch: `feat/epic-05-api-adapter-candidate`
- Adapter path: `security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py`
- Activation: explicit `--conformance-only`
- Supported scope: synthetic `conformance.*` capabilities only
- Authorization: synthetic `authz/conformance/active` only
- State: in-memory test ledger only
- Vendor-neutral conformance: `PASS_SYNTHETIC`
- Execution integration: `NOT_RUN`
- Promotion status: blocked
- Legacy `execute_runbook` / bridge path: unchanged and disconnected
- Runtime declaration: `NO_RUNTIME_CHANGE`

The block must prove conformance, refusal of real capabilities and authorization references,
absence of legacy execution imports/calls and absence of persistent/network/process side effects.
A green result is not production conformance evidence.

''',
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.4.0 | Record repository-local SDK AS_BUILT, merge/CI evidence and fail-closed contract resolution. |",
        "| 2026-08-06 | 1.4.0 | Record repository-local SDK AS_BUILT, merge/CI evidence and fail-closed contract resolution. |\n"
        "| 2026-08-06 | 1.4.1 | Start block 4 API-family candidate in synthetic-only conformance mode with production promotion blocked. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_in_section(
        concepts,
        "  - concept_id: EPIC-05\n",
        "  - concept_id: EPIC-06\n",
        '    current_state: "AS_BUILT for contract, conformance-kit and repository-local SDK blocks. Canonical validation and fingerprint logic are importable without duplication; API, DevSecOps and AI/MCP adapters remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit and SDK blocks; an API-family synthetic-only candidate is IMPLEMENTING with PASS_SYNTHETIC, execution integration NOT_RUN and promotion blocked. DevSecOps and AI/MCP remain NOT_RUN."\n',
    )

    inventory = "docs/architecture/contracts/README.md"
    replace_once(
        inventory,
        "contract, conformance-kit and SDK blocks `AS_BUILT`; adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
        "contract, conformance-kit and SDK blocks `AS_BUILT`; API synthetic candidate `IMPLEMENTING` / `PASS_SYNTHETIC`, execution `NOT_RUN`; other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md)",
    )

    for temporary in (
        ".github/workflows/epic-05-api-candidate-patch-once.yml",
        "tools/tmp_epic05_api_candidate_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
