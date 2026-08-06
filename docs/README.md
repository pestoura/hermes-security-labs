# Documentação — Hermes Security Labs

Navegação canónica da documentação do repositório. Todos os documentos abaixo são
mantidos em Git e são a fonte de verdade. Issues do GitHub são uma vista de trabalho.

## Percursos

| Quero… | Começar em |
| --- | --- |
| Perceber o que é o projeto | [Project overview](project-overview.md) |
| Saber onde está cada coisa | [Repository tour](repository-tour.md) |
| Perceber como o sistema funciona | [Architecture](architecture.md) |
| Pôr o repositório a validar localmente | [Getting started](getting-started.md) |
| Operar laboratórios e deployment | [Operator guide](operator-guide.md) |
| Contribuir com runbooks, labs ou runners | [Contributor guide](contributor-guide.md) |
| Resolver uma falha | [Troubleshooting](troubleshooting.md) |
| Perceber limites de segurança | [Security model](security-model.md) |
| Traduzir siglas e frameworks | [Glossary and references](glossary-and-references.md) |
| Saber quem mantém a documentação | [Documentation governance](documentation-governance.md) |
| Consultar decisões estruturantes | [ADR index](architecture/adr/README.md) |
| Identificar o owner de um contrato | [Canonical contract inventory](architecture/contracts/README.md) |
| Perceber a verdade declarativa e o drift do runtime | [Runtime source-of-truth policy](architecture/runtime-source-of-truth.md) |

## Índice completo

### Documentação canónica

- [Project overview](project-overview.md)
- [Repository tour](repository-tour.md)
- [Architecture](architecture.md)
- [Getting started / tutorial](getting-started.md)
- [Operator guide](operator-guide.md)
- [Contributor guide](contributor-guide.md)
- [Troubleshooting](troubleshooting.md)
- [Security model](security-model.md)
- [Glossary and references](glossary-and-references.md)
- [Documentation governance](documentation-governance.md)

### Roadmap v2

- [Roadmap SVP v2](roadmap/security-validation-platform-v2.md)
- [Platform v2 intent (45 concept epics)](architecture/security-validation-platform-v2-intent.md)
- [Epic catalogue — 45 concept epics](roadmap/epic-catalogue-45.md)
- [Architecture documentation lifecycle](architecture/architecture-documentation-lifecycle.md)
- [Reference architecture](architecture/security-validation-reference-architecture.md)
- [Architecture Decision Records](architecture/adr/README.md)
- [Canonical architecture contract inventory](architecture/contracts/README.md)
- [Runtime source-of-truth policy](architecture/runtime-source-of-truth.md)
- [Framework crosswalk](architecture/framework-crosswalk.md)
- [Security knowledge fabric](architecture/security-knowledge-fabric.md)
- [Continuous content factories](architecture/continuous-content-factories.md)
- [Backlog README](../roadmap/README.md)

### Operação e supply chain

- [Deployment tracking e drift](deployment-tracking.md)
- [GHCR container registry](ghcr-container-registry.md)
- [GHCR private read-only transition](ghcr-private-readonly-transition.md)
- Rollouts GHCR: [VAmPI](ghcr-vampi-pilot.md) · [DVAPI](ghcr-dvapi-rollout.md) ·
  [DVGA](ghcr-dvga-rollout.md) · [NodeGoat](ghcr-nodegoat-rollout.md) ·
  [PyGoat](ghcr-pygoat-rollout.md)
- [Modelo operacional direto GitHub (Fase 2)](phase2-direct-github-operating-model.md)
- [Batch de ambientes Fase 2](phase2-environment-batch.md)

### Camada de segurança

- [Arquitetura consolidada da camada security](../security/docs/architecture.md)
- [Mapeamento de sinais API](../security/docs/api-signals-mapping.md)
- [Migração de packs](../security/docs/migration.md)

### Auditorias e histórico

- [Layout do catálogo](audits/catalog-layout.md)
- [Repositórios substituídos](consolidation/superseded-repositories.md)

## Convenções

- Documentos descritivos e procedimentais em Markdown, sem credenciais, tokens,
  payloads ofensivos nem instruções contra alvos externos.
- Diagramas em Mermaid compatível com GitHub (`flowchart`, `sequenceDiagram`,
  `stateDiagram-v2`).
- Funcionalidades ainda não implementadas são explicitamente marcadas como
  **roadmap**.
