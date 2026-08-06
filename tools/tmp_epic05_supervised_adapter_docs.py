from __future__ import annotations

from pathlib import Path

SELF = Path(__file__)
WORKFLOW = Path(".github/workflows/epic-05-supervised-adapter-docs-once.yml")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


compatibility = Path("platform/runner-protocol/compatibility.yaml")
replace_once(compatibility, 'schema_version: "1.2"', 'schema_version: "1.3"')
replace_once(
    compatibility,
    "      production_effect_claim: none\n    notes: The opt-in API candidates pass synthetic protocol conformance, including durable restart replay in the dedicated candidate, but remain disconnected from execute_runbook and the legacy ProcessBridgeAdapter; no real API capability is integrated.\n",
    "      production_effect_claim: none\n    supervised_process:\n      status: PASS_SYNTHETIC_PROCESS\n      integration_scope: fixed_synthetic_worker_only\n      adapter_path: security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py\n      worker_path: security/packs/api/src/api_pentest_runbooks/synthetic_supervised_worker.py\n      activation_arguments:\n        - --conformance-only\n        - --synthetic-process-only\n        - --durable-ledger\n      durable_claim_before_spawn: PASS_SYNTHETIC_PROCESS\n      async_cancellation: PASS_SYNTHETIC_PROCESS\n      hard_timeout: PASS_SYNTHETIC_PROCESS\n      descendant_residue: fail_closed_inconclusive\n      raw_output_persistence: none\n      sandbox_status: NOT_IMPLEMENTED\n      production_effect_claim: none\n    notes: The opt-in API candidates prove synthetic protocol, durable restart replay and fixed-worker process supervision. They remain disconnected from execute_runbook and the legacy ProcessBridgeAdapter; no real API capability is integrated.\n",
)

contracts = Path("platform/runner-protocol/src/runner_protocol_v2/contracts.py")
replace_once(
    contracts,
    "The SDK is side-effect free. It validates messages, compatibility declarations,\nprogress streams and idempotency fingerprints; it never dispatches or cancels work.\n",
    "Protocol validation helpers are side-effect free. Optional SDK enforcement primitives\nprovide durable idempotency and bounded POSIX process supervision, but never authorize work.\n",
)
replace_once(
    contracts,
    '    if data.get("schema_version") != "1.2":\n        raise ProtocolValidationError("compatibility schema version must be 1.2")\n',
    '    if data.get("schema_version") != "1.3":\n        raise ProtocolValidationError("compatibility schema version must be 1.3")\n',
)
replace_once(
    contracts,
    "    if api.get(\"durable_idempotency\") != durable_expected:\n        raise ProtocolValidationError(\n            \"API durable-idempotency declaration is inconsistent\"\n        )\n\n    repository_root = root.parents[1]\n",
    "    if api.get(\"durable_idempotency\") != durable_expected:\n        raise ProtocolValidationError(\n            \"API durable-idempotency declaration is inconsistent\"\n        )\n\n    supervised_expected = {\n        \"status\": \"PASS_SYNTHETIC_PROCESS\",\n        \"integration_scope\": \"fixed_synthetic_worker_only\",\n        \"adapter_path\": (\n            \"security/packs/api/src/api_pentest_runbooks/\"\n            \"supervised_runner_protocol_adapter.py\"\n        ),\n        \"worker_path\": (\n            \"security/packs/api/src/api_pentest_runbooks/\"\n            \"synthetic_supervised_worker.py\"\n        ),\n        \"activation_arguments\": [\n            \"--conformance-only\",\n            \"--synthetic-process-only\",\n            \"--durable-ledger\",\n        ],\n        \"durable_claim_before_spawn\": \"PASS_SYNTHETIC_PROCESS\",\n        \"async_cancellation\": \"PASS_SYNTHETIC_PROCESS\",\n        \"hard_timeout\": \"PASS_SYNTHETIC_PROCESS\",\n        \"descendant_residue\": \"fail_closed_inconclusive\",\n        \"raw_output_persistence\": \"none\",\n        \"sandbox_status\": \"NOT_IMPLEMENTED\",\n        \"production_effect_claim\": \"none\",\n    }\n    if api.get(\"supervised_process\") != supervised_expected:\n        raise ProtocolValidationError(\n            \"API supervised-process declaration is inconsistent\"\n        )\n\n    repository_root = root.parents[1]\n",
)
replace_once(
    contracts,
    "        (\n            str(durable_expected[\"adapter_path\"]),\n            (\"--conformance-only\", str(durable_expected[\"activation_argument\"])),\n            \"API durable conformance candidate\",\n        ),\n    )\n",
    "        (\n            str(durable_expected[\"adapter_path\"]),\n            (\"--conformance-only\", str(durable_expected[\"activation_argument\"])),\n            \"API durable conformance candidate\",\n        ),\n        (\n            str(supervised_expected[\"adapter_path\"]),\n            tuple(str(value) for value in supervised_expected[\"activation_arguments\"]),\n            \"API supervised synthetic-process candidate\",\n        ),\n    )\n",
)
replace_once(
    contracts,
    "        for argument in required_arguments:\n            if argument not in adapter_source:\n                raise ProtocolValidationError(\n                    f\"{candidate_name} activation argument {argument!r} is not enforced\"\n                )\n\n    not_started_expected = {\n",
    "        for argument in required_arguments:\n            if argument not in adapter_source:\n                raise ProtocolValidationError(\n                    f\"{candidate_name} activation argument {argument!r} is not enforced\"\n                )\n\n    worker_path = (repository_root / str(supervised_expected[\"worker_path\"])).resolve()\n    if repository_root not in worker_path.parents or not worker_path.is_file():\n        raise ProtocolValidationError(\n            \"API supervised synthetic worker path is missing or outside repository\"\n        )\n    worker_source = worker_path.read_text(encoding=\"utf-8\")\n    for forbidden in (\"socket\", \"requests\", \"urllib\", \"execute_runbook\", \"execute_command\"):\n        if forbidden in worker_source:\n            raise ProtocolValidationError(\n                f\"API supervised synthetic worker must not reference {forbidden}\"\n            )\n\n    not_started_expected = {\n",
)

protocol_readme = Path("platform/runner-protocol/README.md")
replace_once(
    protocol_readme,
    "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit and durable transactional idempotency ledger are available; API-family in-memory and durable candidates pass synthetic conformance only; a POSIX supervised-process boundary is implementing with no adapter integration, while real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
    "- Current implementation state: contract, repository-local SDK, vendor-neutral conformance kit, durable transactional idempotency ledger and POSIX process supervisor are available; API-family in-memory and durable candidates pass synthetic conformance, and a fixed-worker supervised candidate is `IMPLEMENTING` with `PASS_SYNTHETIC_PROCESS`; real execution for API, DevSecOps and AI/MCP remains unimplemented.\n",
)
replace_once(
    protocol_readme,
    "authorize, select capabilities, map targets or produce protocol evidence. No existing adapter\nconsumes it. The SDK remains the shared dependency so protocol and lifecycle semantics are not\ncopied per family.\n",
    "authorize, select capabilities, map targets or produce protocol evidence. Only the fixed-worker\nsynthetic-process candidate consumes it; no production adapter does. The SDK remains the shared\ndependency so protocol and lifecycle semantics are not copied per family.\n",
)
replace_once(
    protocol_readme,
    "This is not a sandbox. It provides no cgroup, namespace, seccomp, network, privilege or resource\nquota enforcement and is not connected to any runner adapter. Real capability execution remains\n`NOT_RUN`.\n",
    "This is not a sandbox. It provides no cgroup, namespace, seccomp, network, privilege or resource\nquota enforcement. The API fixed-worker synthetic candidate exercises it without accepting a\ncaller-controlled command; no production adapter consumes it and real capability execution remains\n`NOT_RUN`.\n\n### API supervised synthetic-process candidate\n\nThe block-8 candidate is implemented at\n[`security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`](../../security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py).\nIt requires `--conformance-only`, `--synthetic-process-only` and an external durable ledger. The\nrequest cannot select `argv`, working directory, environment or worker mode. A durable claim is\ncreated before the fixed worker starts; timeout, cancellation and descendant residue are mapped to\nvalidated terminal outcomes, and raw worker streams are replaced by hashes and byte counts.\n\nIts compatibility state is `PASS_SYNTHETIC_PROCESS`, not production conformance. Sandboxing, real\nauthorization lookup, target allowlisting, Evidence Plane integration and real API execution remain\n`NOT_RUN`; promotion remains blocked.\n",
)
replace_once(
    protocol_readme,
    "The in-memory process starts only with `--conformance-only`. The durable candidate at\n[`security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`](../../security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py)\nrequires both `--conformance-only` and `--durable-ledger` with an absolute path outside the\nworking tree. Both accept only synthetic `conformance.*` capabilities and the synthetic\nauthorization reference `authz/conformance/active`. Neither has a network, subprocess, bridge or\nlegacy executor dependency. Any real API capability, real authorization reference or unsupported\ncontrol action fails closed before a durable claim.\n",
    "The in-memory process starts only with `--conformance-only`. The durable candidate at\n[`security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py`](../../security/packs/api/src/api_pentest_runbooks/durable_runner_protocol_adapter.py)\nrequires both `--conformance-only` and `--durable-ledger`. The supervised candidate additionally\nrequires `--synthetic-process-only` and invokes only the fixed repository worker. All candidates\naccept only synthetic capabilities and `authz/conformance/active`; real API capabilities and real\nauthorization references fail closed before an executable effect. None references the bridge or\nlegacy executor.\n",
)
replace_once(
    protocol_readme,
    "- no live process cancellation or customer-target execution.\n",
    "- supervised timeout/cancellation limited to the fixed synthetic worker;\n- no customer-target or real security-tool execution.\n",
)
replace_once(
    protocol_readme,
    "- no runner adapter or gateway enforcement;\n",
    "- no production runner adapter or gateway enforcement;\n",
)

api_readme = Path("security/packs/api/README.md")
replace_once(
    api_readme,
    "O pack inclui dois candidatos opt-in destinados exclusivamente ao conformance kit do Runner\nProtocol v2:\n\n- `src/api_pentest_runbooks/runner_protocol_adapter.py`: estado apenas em memória;\n- `src/api_pentest_runbooks/durable_runner_protocol_adapter.py`: integração sintética com o\n  `SQLiteIdempotencyLedger`, usando uma base explícita fora do repositório.\n\nAmbos:\n\n- só arrancam com `--conformance-only`;\n- aceitam apenas capabilities sintéticas `conformance.*`;\n- não importam nem chamam `execute_runbook`, `ProcessBridgeAdapter` ou `execute_command`;\n- não executam rede, subprocessos ou ferramentas de segurança;\n- recusam capabilities e referências de autorização reais;\n- estão desligados do caminho operacional descrito abaixo.\n\nO candidato durável exige também `--durable-ledger <caminho-absoluto>`, faz claim antes do\nefeito sintético e suporta replay após reinício. Claims `IN_PROGRESS` não são recuperadas\nautomaticamente. Ver\n[`docs/runner-protocol-durable-candidate.md`](docs/runner-protocol-durable-candidate.md).\n\nO resultado continua limitado a `PASS_SYNTHETIC`: a integração de execução é `NOT_RUN` e a\npromoção permanece bloqueada. Nenhum candidato representa um runner API operacional nem altera\no comportamento existente do pack.\n",
    "O pack inclui três candidatos opt-in destinados exclusivamente a validação sintética do Runner\nProtocol v2:\n\n- `src/api_pentest_runbooks/runner_protocol_adapter.py`: estado apenas em memória;\n- `src/api_pentest_runbooks/durable_runner_protocol_adapter.py`: replay sintético através do\n  `SQLiteIdempotencyLedger`;\n- `src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`: processo sintético fixo,\n  claim durável anterior ao spawn e timeout/cancelamento através do supervisor POSIX.\n\nTodos recusam capabilities e referências de autorização reais e permanecem desligados de\n`execute_runbook`, `ProcessBridgeAdapter`, `execute_command`, redes, laboratórios e ferramentas de\nsegurança. Os dois primeiros não executam subprocessos. O terceiro exige também\n`--synthetic-process-only` e só pode invocar `synthetic_supervised_worker.py` com modos fixos; o\npedido não consegue definir comando, argumentos, diretório, ambiente ou alvo.\n\nO candidato durável suporta replay após reinício. O candidato supervisionado acrescenta processo\nfixo, timeout forte, cancelamento assíncrono, limpeza de descendentes e outcomes sem stdout/stderr\nbruto. Claims `IN_PROGRESS` não são recuperadas automaticamente. Ver\n[`docs/runner-protocol-durable-candidate.md`](docs/runner-protocol-durable-candidate.md) e\n[`docs/runner-protocol-supervised-candidate.md`](docs/runner-protocol-supervised-candidate.md).\n\nOs estados permanecem limitados a `PASS_SYNTHETIC` e `PASS_SYNTHETIC_PROCESS`: a execução de\nprodução é `NOT_RUN`, não existe sandbox completa e a promoção continua bloqueada. Nenhum\ncandidato representa um runner API operacional nem altera o caminho existente do pack.\n",
)

epic = Path("docs/roadmap/epics/EPIC-05-runner-protocol-v2.md")
replace_once(epic, "| Document version | 1.8.0 |", "| Document version | 1.8.1 |")
replace_once(
    epic,
    "cleanup but remains disconnected from every adapter. `FINAL` remains false: production execution\nintegration is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`, and\nbounded live cancellation has not been demonstrated through a Runner Protocol adapter.\n",
    "cleanup. Block 8 is now `IMPLEMENTING`: an API-family fixed-worker synthetic candidate consumes\nthe ledger and supervisor, proving claim-before-spawn, timeout, asynchronous cancellation and\nfail-closed residue handling without real capabilities. `FINAL` remains false: production\nexecution integration is `NOT_RUN`, promotion is blocked, DevSecOps and AI/MCP remain `NOT_RUN`,\nand no sandboxed real capability has been demonstrated.\n",
)
replace_once(
    epic,
    "## 15. As-built / final architecture\n",
    "### Block 8 — API supervised synthetic-process integration (`IMPLEMENTING`)\n\n- Branch: `feat/epic-05-api-supervised-synthetic-adapter`\n- Adapter: `security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`\n- Worker: `security/packs/api/src/api_pentest_runbooks/synthetic_supervised_worker.py`\n- Activation: `--conformance-only --synthetic-process-only --durable-ledger <absolute-path>`\n- Scope: fixed synthetic worker modes only\n- Durable claim: before process creation\n- Cancellation: asynchronous progress then bounded process-group cleanup\n- Timeout: hard timeout enforced by the POSIX supervisor\n- Residue: `INCONCLUSIVE`, never `PASS`\n- Output: stream hashes, lengths and supervision metadata; no raw stdout/stderr\n- Compatibility status: `PASS_SYNTHETIC_PROCESS`\n- Sandbox status: `NOT_IMPLEMENTED`\n- Production API execution: `NOT_RUN`\n- Promotion status: blocked\n- Runtime declaration: `NO_RUNTIME_CHANGE`\n\nThe block must prove that request input cannot form a command, completed outcomes replay without\na second process, cancellation persists across restart, and cleanup uncertainty cannot become\nsuccess. It remains synthetic process-level evidence only.\n\n## 15. As-built / final architecture\n",
)
replace_once(
    epic,
    "  SUP -. no adapter consumer .-> RUN\n",
    "  SUP --> SAPI[API fixed-worker supervised candidate]\n  SAPI --> LEDGER\n  SAPI -. no production capability .-> RUN\n",
)
replace_once(
    epic,
    "runner adapter dispatches work through the supervisor; its process side effects are limited to\ncontrolled repository tests and do not access networks, containers or laboratories.\n",
    "the fixed-worker synthetic API candidate dispatches controlled repository test processes through\nthe supervisor. No production adapter, network, container, laboratory or customer target is used.\n",
)
replace_once(
    epic,
    "| 2026-08-06 | 1.8.0 | Record supervised process boundary AS_BUILT with adapter integration and real execution NOT_RUN. |\n",
    "| 2026-08-06 | 1.8.0 | Record supervised process boundary AS_BUILT with adapter integration and real execution NOT_RUN. |\n| 2026-08-06 | 1.8.1 | Start fixed-worker API supervised synthetic-process integration with production execution blocked. |\n",
)

catalogue = Path("roadmap/epics/security-validation-platform-v2-concepts.yaml")
replace_once(
    catalogue,
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate, API durable synthetic restart replay and POSIX supervised-process boundary. No adapter consumes the supervisor. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
    '    current_state: "AS_BUILT for contract, conformance-kit, SDK, durable ledger, API in-memory candidate, API durable synthetic restart replay and POSIX process supervisor. Fixed-worker API supervised synthetic-process integration is IMPLEMENTING with PASS_SYNTHETIC_PROCESS. Production execution remains NOT_RUN, promotion blocked, and DevSecOps/AI-MCP NOT_RUN."\n',
)

inventory = Path("docs/architecture/contracts/README.md")
replace_once(
    inventory,
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK, durable ledger and POSIX process-supervision boundary `AS_BUILT`; API in-memory and durable synthetic candidates `AS_BUILT` / `PASS_SYNTHETIC`; no adapter consumes supervision and production execution is `NOT_RUN`; other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout, cancellation or verified cleanup is a normalized non-success outcome |\n",
    "| Runner dispatch and result | internal execution boundary | Runner Protocol owner / `SVP2-B-02` | gateway → runner → gateway | Runner Protocol v2 (`EPIC-05`) | contract, conformance-kit, SDK, durable ledger and POSIX process supervisor `AS_BUILT`; API in-memory/durable candidates `PASS_SYNTHETIC`; fixed-worker supervised candidate `IMPLEMENTING` / `PASS_SYNTHETIC_PROCESS`; production execution and other adapters `NOT_RUN`; [`platform/runner-protocol/`](../../../platform/runner-protocol/README.md) | missing correlation, incompatibility, timeout, cancellation or verified cleanup is a normalized non-success outcome |\n",
)

SELF.unlink()
WORKFLOW.unlink()
