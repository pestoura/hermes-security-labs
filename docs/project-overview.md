# Project overview

## Propósito

`hermes-security-labs` é a plataforma segregada de laboratórios de cibersegurança do
Hermes. Combina três coisas num único monorepo:

1. **Alvos controlados** — laboratórios vulneráveis descartáveis, definidos por
   manifesto e executados localmente.
2. **Conhecimento de teste** — uma biblioteca determinística de runbooks, campanhas,
   políticas e bindings.
3. **Disciplina operacional** — lifecycle, deployment tracking, drift detection,
   evidência sanitizada e gates de CI.

O objetivo é permitir validação de segurança **repetível, auditável e contida**, sem
improviso e sem tocar em sistemas fora de âmbito.

## Público-alvo

- **Operador** — executa laboratórios e campanhas no host Hermes.
- **Contribuidor** — adiciona ou altera runbooks, laboratórios, adapters e runners.
- **Auditor / revisor** — verifica evidência, âmbito, gates e proveniência.

## Limites

Este repositório **não** é um framework de exploração ofensiva genérico, não gere
alvos de produção e não contém segredos, resultados brutos, imagens runtime,
credenciais, tokens nem dados pessoais.

Fora de âmbito por regra:

- alvos fora de um laboratório registado;
- LAN doméstica, Home Assistant, SPMS ou o próprio host Hermes como alvo;
- egress permanente;
- recursos cloud reais fora de contas sandbox autorizadas;
- deployment automático de GitHub para o Hermes.

## O que a plataforma já faz

| Capacidade | Estado |
| --- | --- |
| Catálogo machine-readable de laboratórios (`labctl`) | implementado |
| Catálogo e validação de 370 runbooks (`securityctl`) | implementado |
| Bindings laboratório ↔ pack ↔ campanha | implementado |
| Lifecycle Docker de laboratórios Web/API e DevSecOps | implementado |
| Kali MCP com 12 ferramentas por STDIO | implementado |
| Deployment tracking, verify, drift-check, rollback | implementado |
| Publicação GHCR de imagens construídas pelo projeto | implementado (5 packages) |
| Adapters calibrados WrongSecrets e PromptMe | implementado |
| Gates de CI: YAML, catálogo, shell, self-tests, gitleaks | implementado |

## O que pertence ao roadmap v2

Marcado como **roadmap** em toda a documentação. Não está implementado:

- gateway de execução tipado e Kali MCP Protocol v2;
- Runner Protocol v2 com correlação, cancelamento e erros normalizados;
- Evidence Plane v2 com chain of custody e replay;
- capability registry assinado e image factory;
- security knowledge fabric e Security Knowledge API;
- threat-informed validation, purple team e attack graph;
- níveis de intrusividade L0–L4 como política executável;
- content factories e Lab Schema v2;
- expansão para Kubernetes, identidade, cloud, mobile e IoT/OT.

Fonte canónica: [roadmap SVP v2](roadmap/security-validation-platform-v2.md) e o
backlog em [`roadmap/epics/security-validation-platform-v2.yaml`](../roadmap/epics/security-validation-platform-v2.yaml).

## Estado dos 370 runbooks

| Domínio | Pack | Runbooks | Contrato de schema |
| --- | --- | --- | --- |
| API | `security/packs/api` | 150 | `ApiPentestRunbook` |
| DevSecOps | `security/packs/devsecops` | 120 | `SecurityRunbook` |
| IA / MCP | `security/packs/ai-mcp` | 100 | `SecurityRunbook` |
| **Total** | — | **370** | — |

Gate canónico:

```bash
python security/tools/securityctl.py validate
# OK	api=150 devsecops=120 ai-mcp=100 total=370 warnings=0
```

Todos os runbooks permanecem `experimental` até serem calibrados com controlo
positivo e negativo, evidência sanitizada, repetibilidade e análise de falsos
positivos. A convergência dos dois contratos de schema é uma migração separada e
não deve reescrever semântica existente em silêncio.

## Relação `platform/` ↔ `security/`

```text
platform/   = onde os targets vivem
security/   = como os targets são testados
```

A fronteira é deliberada:

- `security/` **pode** referenciar IDs de laboratório;
- `platform/` **não pode** importar definições de runbook;
- um runbook nunca vive dentro da pasta de um laboratório, porque pode ser
  reutilizado por vários targets e campanhas.

A ligação entre os dois lados é feita exclusivamente por
[`security/bindings/labs.yaml`](../security/bindings/labs.yaml).

## Ver também

- [Repository tour](repository-tour.md)
- [Architecture](architecture.md)
- [Security model](security-model.md)
