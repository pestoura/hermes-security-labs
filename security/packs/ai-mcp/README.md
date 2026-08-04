> **Localização canónica:** `security/packs/ai-mcp` no monorepo `pestoura/hermes-security-labs`.  
> Importado de `pestoura/ai-mcp-security-runbooks@24078938b2584674f0e075e644677ec1f18b12a9`; o repositório autónomo é apenas histórico de migração.

# AI/MCP Security Runbooks

Biblioteca versionada de **100 runbooks machine-readable** para o domínio `ai-mcp`.

Cada runbook é um ficheiro YAML individual em `runbooks/`. Os YAML são a fonte canónica; CSV e relatórios são derivados.

## Cobertura

- `agent-discovery`: 6
- `direct-prompt-injection`: 14
- `indirect-prompt-injection`: 12
- `tool-poisoning`: 12
- `excessive-agency`: 10
- `mcp-authorization`: 12
- `rag-poisoning`: 10
- `memory-security`: 8
- `exfiltration`: 10
- `output-integrity`: 6

## Definição materializada

Cada runbook tem ID único, seletores de target, capacidades, limites de risco, três passos tipados, critérios específicos de avaliação, requisitos determinísticos de evidência e finding de saída. Nenhum runbook contém campos livres `shell`, `script`, `command` ou `argv`.

## Estado de validação

As definições estão estruturalmente completas e validadas em CI. Permanecem `experimental` até os controlos positivos e negativos serem calibrados nos laboratórios autorizados. Completude estrutural não prova deteção operacional num agente ou servidor MCP real.

## Comandos no monorepo

```bash
cd security/packs/ai-mcp
python tools/validate_pack.py
pytest -q
python tools/export_catalog.py --output dist/catalog.csv
```

A ligação aos laboratórios é canónica em `../../bindings/labs.yaml`.
