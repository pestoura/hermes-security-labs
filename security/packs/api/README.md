> **Localização canónica:** `security/packs/api` no monorepo `pestoura/hermes-security-labs`.  
> Importado de `pestoura/api-pentest-runbooks@3273ec9f8352597758ba2c3f4ddb7ead1e59c926`; o repositório autónomo é apenas histórico de migração.

# API Pentest Runbooks

Biblioteca canónica e machine-readable de runbooks de pentest autorizado a APIs Web, desenhada para planeamento pelo Hermes e execução controlada através do Kali MCP.

## Estado

A versão `v0.1.0-alpha` contém a fundação do motor, políticas e 150 runbooks individuais. Estes runbooks preservam nesta migração os critérios de avaliação genéricos do pack de origem; continuam `experimental` e pendentes de implementação/calibração específica, evidência e análise de falsos positivos.

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
