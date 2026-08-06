> **Localização canónica:** `security/packs/api` no monorepo `pestoura/hermes-security-labs`.  
> Importado de `pestoura/api-pentest-runbooks@3273ec9f8352597758ba2c3f4ddb7ead1e59c926`; o repositório autónomo é apenas histórico de migração.

# API Pentest Runbooks

Biblioteca canónica e machine-readable de runbooks de pentest autorizado a APIs Web, desenhada para planeamento pelo Hermes e execução controlada através do Kali MCP.

## Estado

A versão `v0.1.0-alpha` contém a fundação do motor, políticas e 150 runbooks individuais. Estes runbooks preservam nesta migração os critérios de avaliação genéricos do pack de origem; continuam `experimental` e pendentes de implementação/calibração específica, evidência e análise de falsos positivos.

## Runner Protocol v2 — candidatos isolados

O pack inclui três candidatos opt-in destinados exclusivamente a validação sintética do Runner
Protocol v2:

- `src/api_pentest_runbooks/runner_protocol_adapter.py`: estado apenas em memória;
- `src/api_pentest_runbooks/durable_runner_protocol_adapter.py`: replay sintético através do
  `SQLiteIdempotencyLedger`;
- `src/api_pentest_runbooks/supervised_runner_protocol_adapter.py`: processo sintético fixo,
  claim durável anterior ao spawn e timeout/cancelamento através do supervisor POSIX.

Todos recusam capabilities e referências de autorização reais e permanecem desligados de
`execute_runbook`, `ProcessBridgeAdapter`, `execute_command`, redes, laboratórios e ferramentas de
segurança. Os dois primeiros não executam subprocessos. O terceiro exige também
`--synthetic-process-only` e só pode invocar `synthetic_supervised_worker.py` com modos fixos; o
pedido não consegue definir comando, argumentos, diretório, ambiente ou alvo.

O candidato durável suporta replay após reinício. O candidato supervisionado acrescenta processo
fixo, timeout forte, cancelamento assíncrono, limpeza de descendentes e outcomes sem stdout/stderr
bruto. Claims `IN_PROGRESS` não são recuperadas automaticamente. Ver
[`docs/runner-protocol-durable-candidate.md`](docs/runner-protocol-durable-candidate.md) e
[`docs/runner-protocol-supervised-candidate.md`](docs/runner-protocol-supervised-candidate.md).

Os estados permanecem limitados a `PASS_SYNTHETIC` e `PASS_SYNTHETIC_PROCESS`: a execução de
produção é `NOT_RUN`, não existe sandbox completa e a promoção continua bloqueada. Nenhum
candidato representa um runner API operacional nem altera o caminho existente do pack.

## Princípio operacional

```text
Hermes master/planner
  -> seleciona campanha e runbooks
Policy engine
  -> valida âmbito, risco e limites
Executor determinístico
  -> cria chamadas MCP tipificadas
Kali MCP execute_command
  -> invoca apenas o runner fixo
Kali runner allowlisted
  -> executa ações reais e recolhe evidência
```

O modelo de linguagem nunca fornece comandos shell livres. Cada passo referencia um `handler` e um `profile` conhecidos. O adapter envia ao MCP apenas um comando fixo para o runner, com um payload JSON codificado.

## Quick start no monorepo

```bash
cd security/packs/api
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
api-pentest-runbooks validate
api-pentest-runbooks list --category authorization
pytest
```

## Limites de segurança

- Apenas sistemas expressamente autorizados.
- Âmbito validado no planner, policy engine, adapter e runner.
- Sem shell arbitrária, `eval`, templates de comandos editáveis pelo LLM ou expansão de variáveis pelo shell.
- Produção bloqueia runbooks não marcados como `production_safe`.
- Credenciais são referências externas e nunca são persistidas no catálogo.
- Resultados brutos e segredos não pertencem ao Git.

## Laboratórios

A ligação aos laboratórios é canónica em `../../bindings/labs.yaml`. O laboratório deve estar ativo, com Kali ligado à rede isolada, antes da execução.

## Estrutura

```text
runbooks/       150 YAML canónicos
campaigns/      seleção e ordenação de runbooks
schemas/        contratos JSON Schema
src/            loader, validator, planner, policy e executor
runner/         runner a instalar/montar no Kali
policies/       perfis laboratory, staging e production
docs/           arquitetura, DSL e plano de validação
tests/          testes estruturais e de segurança
```

Ver também [SECURITY.md](SECURITY.md) e [docs/validation-plan.md](docs/validation-plan.md).
