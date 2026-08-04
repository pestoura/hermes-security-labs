# Security testing layer

Este diretório define **como os targets são testados**. Os targets, runtimes, redes e lifecycle permanecem em [`../platform/`](../platform/).

```text
platform/   targets, runtimes, isolamento e lifecycle
security/   runbooks, campanhas, políticas, adapters, bindings e calibração
```

## Estrutura

```text
security/
├── core/                 motor determinístico e contratos comuns
├── packs/
│   ├── api/              150 runbooks API
│   ├── devsecops/        120 runbooks DevSecOps
│   └── ai-mcp/           100 runbooks IA/MCP
├── bindings/             ligação canónica entre packs, campanhas e laboratórios
├── catalog/              manifesto e catálogos derivados
├── docs/                 arquitetura, migração e operação
├── tools/securityctl.py  CLI unificado de consulta e validação
└── tests/                testes transversais do monorepo
```

## Fonte de verdade

- Um runbook existe apenas no respetivo `security/packs/<domínio>/runbooks/`.
- Um laboratório existe apenas em `platform/environments/`.
- A relação entre ambos existe apenas em `security/bindings/labs.yaml`.
- Catálogos JSON/CSV são derivados e não constituem fonte canónica.
- Evidência runtime, credenciais, payloads sensíveis e resultados brutos não pertencem ao Git.

## Comandos

```bash
python security/tools/securityctl.py validate
python security/tools/securityctl.py list
python security/tools/securityctl.py list --domain devsecops
python security/tools/securityctl.py labs
python security/tools/securityctl.py coverage
python security/tools/securityctl.py catalog --output /tmp/security-catalog.json
```

## Estado

As definições são versionadas e estruturalmente validadas. A promoção de `experimental` para `candidate` ou `stable` continua dependente de adapters reais, controlos positivos e negativos, repetibilidade, evidência sanitizada e análise de falsos positivos em laboratórios autorizados.
