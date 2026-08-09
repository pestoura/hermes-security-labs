# Hermes Security Labs

Plataforma segregada de laboratórios de cibersegurança para o Hermes, com Kali MCP, ambientes vulneráveis multi-runtime, automação de lifecycle, biblioteca de runbooks e verificação de deployment.

## Documentação

A navegação canónica da documentação está em [`docs/README.md`](docs/README.md).

| Documento | Conteúdo |
| --- | --- |
| [Project overview](docs/project-overview.md) | propósito, limites, estado atual e roadmap |
| [Repository tour](docs/repository-tour.md) | estrutura, fonte de verdade e artefactos ignorados |
| [Architecture](docs/architecture.md) | planos, fluxo de execução e diagramas |
| [Quickstart](docs/quickstart.md) | caminho canónico curto: clone → validate → start → Kali → evidência → destroy |
| [Getting started](docs/getting-started.md) | onboarding e validação local |
| [Operator guide](docs/operator-guide.md) | operação diária, lifecycle e recuperação |
| [Contributor guide](docs/contributor-guide.md) | como contribuir e o que testar |
| [Troubleshooting](docs/troubleshooting.md) | sintomas, diagnóstico e ação |
| [Security model](docs/security-model.md) | autorização, isolamento, redaction e proibições |
| [Glossary and references](docs/glossary-and-references.md) | termos e frameworks |
| [Documentation governance](docs/documentation-governance.md) | owner, versionamento e checklists |

## Modelo operacional

- **GitHub:** fonte de verdade de código, configuração, manifestos, runbooks, campanhas, documentação e workflows.
- **GitHub Container Registry:** armazena imagens Docker/OCI construídas ou adaptadas pelo projeto; o runtime consome apenas digests aceites.
- **Hermes:** host e orquestrador dos laboratórios locais.
- **Docker:** runtime principal para Web/API, DevSecOps, IA/MCP e serviços sintéticos.
- **Kubernetes:** clusters descartáveis com kind/k3d.
- **VM/cloud/emulator:** runtimes preparados por manifesto e ativados apenas quando existirem recursos e autorização.
- **Kali MCP:** mantém as ferramentas ofensivas autorizadas; a segregação é aplicada por rede, target, egress e lifecycle.

O repositório não contém segredos, resultados brutos, imagens runtime, credenciais, tokens ou dados pessoais.

## Arquitetura canónica

```text
platform/   = onde os targets vivem
security/   = como os targets são testados
```

`platform/` gere ambientes, runtimes, redes, isolamento, lifecycle e deployment. `security/` contém o motor determinístico, 370 runbooks, campanhas, políticas, adapters e a ligação canónica aos laboratórios. Um runbook nunca é colocado dentro da pasta de um laboratório porque pode ser reutilizado por vários targets e campanhas.

## Roadmap v2

A visão de evolução para uma *Threat-Informed Continuous Security Validation Platform* está versionada no repositório: [roadmap](docs/roadmap/security-validation-platform-v2.md), [arquitetura de referência](docs/architecture/security-validation-reference-architecture.md), [crosswalk de frameworks](docs/architecture/framework-crosswalk.md), [knowledge fabric](docs/architecture/security-knowledge-fabric.md), [content factories](docs/architecture/continuous-content-factories.md) e [backlog](roadmap/README.md).

## Estrutura

```text
docs/                     arquitetura e políticas operacionais
kali-mcp/                 imagem e Compose do Kali MCP
platform/environments/    manifestos e implementações dos laboratórios
platform/registry.yaml    runtimes, estados e descoberta do catálogo
platform/rollout.yaml     instalação faseada dos ambientes
platform/scripts/         CLI e wrappers de catálogo/lifecycle
platform/schemas/         schema dos manifestos
security/core/            motor e contratos comuns dos runbooks
security/packs/api/       150 runbooks API
security/packs/devsecops/ 120 runbooks DevSecOps
security/packs/ai-mcp/    100 runbooks IA/MCP
security/bindings/        ligação packs/campanhas/laboratórios
security/tools/           CLI unificado e validação transversal
deployment/               deploy, verify, rollback e drift detection
skills/                   instruções do agente Hermes
```

A política de imagens próprias, packages privados, proveniência e consumo por digest está documentada em [`docs/ghcr-container-registry.md`](docs/ghcr-container-registry.md).

Os repositórios autónomos que deram origem ao core e aos packs foram consolidados aqui e estão arquivados em read-only. O registo canónico está em [`docs/consolidation/superseded-repositories.md`](docs/consolidation/superseded-repositories.md).

## Catálogo de laboratórios

A descoberta suporta temporariamente dois layouts:

```text
platform/environments/<category>/<id>.yaml
platform/environments/<category>/<id>/manifest.yaml
```

Comandos read-only:

```bash
./platform/scripts/lab-list.sh
./platform/scripts/lab-list.sh --runtime docker
./platform/scripts/lab-status.sh juice-shop
./platform/scripts/lab-validate.sh
./platform/scripts/lab-plan.sh
./platform/scripts/lab-plan.sh --phase docker-web-api
python3 platform/scripts/lab_audit.py audit --runtime-managed
```

`lab-plan.sh` distingue ambientes já catalogados (`CATALOGUED`) de ambientes ainda por implementar (`PLANNED`).

Não existe wrapper genérico de provisionamento: `lab-start.sh`, `lab-stop.sh`, `lab-reset.sh` e `lab-destroy.sh` são `NOT_IMPLEMENTED` e saem com código `2`. A interface real de lifecycle é por ambiente e está tabelada em [`docs/quickstart.md`](docs/quickstart.md#7-matriz-de-comandos-de-lifecycle).

## Catálogo de segurança

```bash
python security/tools/securityctl.py validate
python security/tools/securityctl.py list
python security/tools/securityctl.py list --domain api
python security/tools/securityctl.py labs
python security/tools/securityctl.py coverage
python security/tools/securityctl.py catalog --output /tmp/security-catalog.json
```

As definições YAML são canónicas. Catálogos JSON/CSV são derivados. Todos os runbooks permanecem `experimental` até serem calibrados com controlo positivo e negativo, evidência sanitizada, repetibilidade e análise de falsos positivos.

## Fases de expansão

1. Baseline, catálogo e Juice Shop end-to-end.
2. Web e API em Docker.
3. DevSecOps, supply chain e IA/MCP.
4. Kubernetes com kind/k3d.
5. Máquinas virtuais, infraestrutura, redes e Active Directory.
6. Cloud sandbox, mobile, IoT, firmware e OT/ICS.

A adoção do GHCR é uma melhoria transversal de supply chain e não uma fase autónoma. Começa com um piloto VAmPI e é aplicada gradualmente aos ambientes construídos pelo projeto.

A execução normal não concede egress permanente, não publica ambientes na LAN e liga o Kali apenas à rede do laboratório ativo. O Kali deve ser desligado dessa rede no final de cada execução.

## Fluxo de alteração

```text
issue → branch → commit → pull request → CI → revisão → merge
      → build/publicação GHCR quando aplicável → deployment local → evidências
```

Alterações que acrescentem um laboratório e runbooks associados devem atualizar, na mesma PR, `platform/environments/`, `security/packs/` e `security/bindings/labs.yaml` quando aplicável.

Não existe deployment automático do GitHub para o Hermes nem self-hosted runner com acesso ao Docker socket.
