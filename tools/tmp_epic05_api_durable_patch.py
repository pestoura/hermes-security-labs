from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    replace_once(path, marker, content + marker)


def main() -> None:
    Path("platform/runner-protocol/compatibility.yaml").write_text(
        '''schema_version: "1.2"
protocol:
  name: runner-protocol
  version: "2.0.0"
  status: contract_only

compatibility_rules:
  major_version: exact_match
  unknown_major: fail_closed
  unknown_message_type: fail_closed
  invalid_schema: fail_closed
  progress_default: optional
  terminal_outcome: mandatory
  terminal_evidence_reference: mandatory
  authorization_source: hermes_control_plane

conformance_kit:
  status: available
  transport: json_lines
  execution_model: isolated_candidate_process
  reference_adapter: test_only
  report_schema: schemas/conformance-report.schema.json
  promotion_effect: none
  required_verdict_for_promotion: PASS

runner_families:
  - id: api
    implementation_status: candidate
    protocol_status: conformance_only
    conformance: PASS_SYNTHETIC
    execution_integration: NOT_RUN
    promotion_status: blocked
    supported_scope: synthetic_conformance_only
    activation: explicit_flag
    adapter_path: security/packs/api/src/api_pentest_runbooks/runner_protocol_adapter.py
    activation_argument: --conformance-only
    durable_idempotency:
      status: PASS_SYNTHETIC
      integration_scope: synthetic_conformance_only
      adapter_path: security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py
      activation_argument: --durable-ledger
      storage_requirement: absolute_path_outside_working_tree
      restart_replay: PASS_SYNTHETIC
      abandoned_claim_reclaim: blocked
      production_effect_claim: none
    notes: The opt-in API candidates pass synthetic protocol conformance, including durable restart replay in the dedicated candidate, but remain disconnected from execute_runbook and the legacy ProcessBridgeAdapter; no real API capability is integrated.
  - id: devsecops
    implementation_status: not_started
    protocol_status: contract_only
    conformance: NOT_RUN
    execution_integration: NOT_RUN
    promotion_status: blocked
    supported_scope: none
    activation: none
    adapter_path: null
    activation_argument: null
    notes: Existing DevSecOps pack semantics are unchanged; no Runner Protocol adapter exists.
  - id: ai-mcp
    implementation_status: not_started
    protocol_status: contract_only
    conformance: NOT_RUN
    execution_integration: NOT_RUN
    promotion_status: blocked
    supported_scope: none
    activation: none
    adapter_path: null
    activation_argument: null
    notes: Existing AI/MCP pack semantics are unchanged; no Runner Protocol adapter exists.

migration_gates:
  - schema_validation
  - semantic_validation
  - correlation_propagation
  - idempotency_replay_test
  - cancellation_timeout_test
  - evidence_reference_test
  - secret_redaction_test
  - conformance_report_pass
  - human_review_before_promotion

runtime_declaration: NO_RUNTIME_CHANGE
''',
        encoding="utf-8",
    )

    contracts = "platform/runner-protocol/src/runner_protocol_v2/contracts.py"
    replace_once(
        contracts,
        '    if data.get("schema_version") != "1.1":\n        raise ProtocolValidationError("compatibility schema version must be 1.1")\n',
        '    if data.get("schema_version") != "1.2":\n        raise ProtocolValidationError("compatibility schema version must be 1.2")\n',
    )
    replace_once(
        contracts,
        '''    repository_root = root.parents[1]
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
''',
        '''    durable_expected = {
        "status": "PASS_SYNTHETIC",
        "integration_scope": "synthetic_conformance_only",
        "adapter_path": (
            "security/packs/api/src/api_pentest_runbooks/"
            "durable_runner_protocol_adapter.py"
        ),
        "activation_argument": "--durable-ledger",
        "storage_requirement": "absolute_path_outside_working_tree",
        "restart_replay": "PASS_SYNTHETIC",
        "abandoned_claim_reclaim": "blocked",
        "production_effect_claim": "none",
    }
    if api.get("durable_idempotency") != durable_expected:
        raise ProtocolValidationError(
            "API durable-idempotency declaration is inconsistent"
        )

    repository_root = root.parents[1]
    candidate_declarations = (
        (
            str(api["adapter_path"]),
            (str(api["activation_argument"]),),
            "API conformance candidate",
        ),
        (
            str(durable_expected["adapter_path"]),
            ("--conformance-only", str(durable_expected["activation_argument"])),
            "API durable conformance candidate",
        ),
    )
    for relative_path, required_arguments, candidate_name in candidate_declarations:
        adapter_path = (repository_root / relative_path).resolve()
        if repository_root not in adapter_path.parents or not adapter_path.is_file():
            raise ProtocolValidationError(
                f"{candidate_name} path is missing or outside repository"
            )
        adapter_source = adapter_path.read_text(encoding="utf-8")
        for forbidden in ("execute_runbook", "execute_command"):
            if forbidden in adapter_source:
                raise ProtocolValidationError(
                    f"{candidate_name} must not reference {forbidden}"
                )
        for argument in required_arguments:
            if argument not in adapter_source:
                raise ProtocolValidationError(
                    f"{candidate_name} activation argument {argument!r} is not enforced"
                )
''',
    )

    api_readme = "security/packs/api/README.md"
    replace_once(
        api_readme,
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
        '''## Runner Protocol v2 — candidatos isolados

O pack inclui dois candidatos opt-in destinados exclusivamente ao conformance kit do Runner
Protocol v2:

- `src/api_pentest_runbooks/runner_protocol_adapter.py`: estado apenas em memória;
- `src/api_pentest_runbooks/durable_runner_protocol_adapter.py`: integração sintética com o
  `SQLiteIdempotencyLedger`, usando uma base explícita fora do repositório.

Ambos:

- só arrancam com `--conformance-only`;
- aceitam apenas capabilities sintéticas `conformance.*`;
- não importam nem chamam `execute_runbook`, `ProcessBridgeAdapter` ou `execute_command`;
- não executam rede, subprocessos ou ferramentas de segurança;
- recusam capabilities e referências de autorização reais;
- estão desligados do caminho operacional descrito abaixo.

O candidato durável exige também `--durable-ledger <caminho-absoluto>`, faz claim antes do
efeito sintético e suporta replay após reinício. Claims `IN_PROGRESS` não são recuperadas
automaticamente. Ver
[`docs/runner-protocol-durable-candidate.md`](docs/runner-protocol-durable-candidate.md).

O resultado continua limitado a `PASS_SYNTHETIC`: a integração de execução é `NOT_RUN` e a
promoção permanece bloqueada. Nenhum candidato representa um runner API operacional nem altera
o comportamento existente do pack.

''',
    )

    runner_readme = "platform/runner-protocol/README.md"
    replace_once(
        runner_readme,
        "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; an API-family candidate passes synthetic conformance only, while durable-ledger adapter integration and real execution for API, DevSecOps and AI/MCP remain unimplemented.",
        "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; API-family in-memory and durable candidates pass synthetic conformance only, while real execution for API, DevSecOps and AI/MCP remains unimplemented.",
    )
    replace_once(
        runner_readme,
        "only caller-supplied idempotency state and validated terminal outcomes. No adapter uses the ledger\nyet. The SDK remains the shared dependency so protocol semantics are not copied per family.\n",
        "only caller-supplied idempotency state and validated terminal outcomes. The API durable synthetic\ncandidate uses it solely for conformance and restart-replay tests. The SDK remains the shared\ndependency so protocol semantics are not copied per family.\n",
    )
    replace_once(
        runner_readme,
        "- the three existing runner families remain `contract_only` until adapters and conformance evidence are integrated.\n",
        "- API remains `conformance_only`; DevSecOps and AI/MCP remain `contract_only` until adapters and conformance evidence are integrated.\n",
    )
    replace_once(
        runner_readme,
        '''The process starts only with `--conformance-only`, accepts only synthetic `conformance.*`
capabilities and the synthetic authorization reference `authz/conformance/active`, and uses an
in-memory ledger. It has no network, subprocess, file, bridge or legacy executor dependency.
Any real API capability, real authorization reference or unsupported control action fails closed.
''',
        '''The in-memory process starts only with `--conformance-only`. The durable candidate at
[`security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`](../../security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py)
requires both `--conformance-only` and `--durable-ledger` with an absolute path outside the
working tree. Both accept only synthetic `conformance.*` capabilities and the synthetic
authorization reference `authz/conformance/active`. Neither has a network, subprocess, bridge or
legacy executor dependency. Any real API capability, real authorization reference or unsupported
control action fails closed before a durable claim.
''',
    )
    replace_once(
        runner_readme,
        "- no persistent idempotency ledger;\n",
        "- durable persistence limited to synthetic conformance and disposable external SQLite state;\n",
    )
    replace_once(
        runner_readme,
        "- no adapter integration of the durable idempotency ledger;\n",
        "- no production adapter integration of the durable idempotency ledger;\n",
    )

    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.6.0 |", "| Document version | 1.6.1 |")
    replace_once(
        epic,
        """again on `main`. `FINAL` remains false: no runner consumes the durable ledger, production
execution integration is `NOT_RUN`, promotion is blocked, and bounded live cancellation
has not been demonstrated against real execution.
""",
        """again on `main`. Block 6 is now `IMPLEMENTING`: a separate API-family synthetic candidate
uses the durable ledger for restart replay without connecting to real capabilities or the legacy
executor. `FINAL` remains false: production execution integration is `NOT_RUN`, promotion is
blocked, and bounded live cancellation has not been demonstrated against real execution.
""",
    )
    insert_before(
        epic,
        "## 15. As-built / final architecture\n",
        '''### Block 6 — API durable synthetic integration (`IMPLEMENTING`)

- Branch: `feat/epic-05-api-durable-ledger-integration`
- Candidate path: `security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`
- Activation: `--conformance-only --durable-ledger <absolute-path>`
- Scope: synthetic `conformance.*` only
- Authorization: synthetic `authz/conformance/active` only
- Durable claim: before the synthetic effect path
- Restart replay: validated with a new candidate instance over the same database
- Uncertain `IN_PROGRESS`: refused; automatic reclaim blocked
- Real API execution: `NOT_RUN`
- Legacy executor and bridge: unchanged and disconnected
- Promotion status: blocked
- Runtime declaration: `NO_RUNTIME_CHANGE`

The block must pass the vendor-neutral conformance kit with disposable durable state and prove
that restart replay does not increase the synthetic effect counter. This remains synthetic
effect-level evidence only.

''',
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.6.0 | Record durable transactional idempotency ledger AS_BUILT with adapter integration NOT_RUN. |",
        "| 2026-08-06 | 1.6.0 | Record durable transactional idempotency ledger AS_BUILT with adapter integration NOT_RUN. |\n"
        "| 2026-08-06 | 1.6.1 | Start API durable synthetic integration with restart replay and production execution blocked. |",
    )

    concepts = "roadmap/epics/security-validation-platform-v2-concepts.yaml"
    replace_once(
        concepts,
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK, API synthetic candidate and durable idempotency-ledger blocks. API execution and durable-ledger adapter integration remain NOT_RUN; promotion is blocked; DevSecOps and AI/MCP remain NOT_RUN."\n',
        '    current_state: "AS_BUILT for contract, conformance-kit, SDK, API synthetic candidate and durable ledger; API durable synthetic restart-replay integration is IMPLEMENTING. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    )

    for temporary in (
        ".github/workflows/epic-05-api-durable-patch-once.yml",
        "tools/tmp_epic05_api_durable_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
