# Repository tour

Árvore comentada dos diretórios principais, com a fonte de verdade de cada área e o
que nunca deve ser editado diretamente.

## Árvore

```text
.
├── README.md                       porta de entrada do repositório
├── CONTRIBUTING.md                 regras mínimas de contribuição
├── SECURITY.md                     política de segredos e reporte
├── CHANGELOG.md                    histórico de alterações relevantes
├── Makefile                        atalhos de validação (validate, compose, fmt)
├── compose.yaml                    Compose de topo do ambiente base
├── Dockerfile                      imagem auxiliar do repositório
├── .env.example                    modelo de variáveis; nunca comitar .env real
│
├── docs/                           documentação canónica (este tour incluído)
│   ├── README.md                   navegação canónica
│   ├── architecture/               arquitetura de referência do roadmap v2
│   ├── roadmap/                    visão, fases e releases SVP v2
│   ├── audits/                     auditorias pontuais
│   └── consolidation/              registo de repositórios substituídos
│
├── roadmap/                        backlog machine-readable
│   ├── README.md                   convenções de IDs, pilares e fases
│   ├── epics/                      YAML dos epics SVP2-<A-L>-<NN>
│   └── tests/                      testes de integridade do backlog
│
├── schemas/                        schemas JSON transversais (backlog-epic)
│
├── platform/                       ONDE OS TARGETS VIVEM
│   ├── environments/<cat>/         manifestos e implementações dos laboratórios
│   ├── registry.yaml               runtimes, estados e descoberta do catálogo
│   ├── rollout.yaml                instalação faseada dos ambientes
│   ├── schemas/                    schema dos manifestos de laboratório
│   ├── scripts/                    labctl.py e wrappers lab-*.sh do lifecycle
│   ├── runtime/                    utilitários de runtime (fetch seguro, safe-lab)
│   └── runtimes/                   definições de runtime por família
│
├── security/                       COMO OS TARGETS SÃO TESTADOS
│   ├── core/                       motor e contratos comuns dos runbooks
│   ├── packs/api/                  150 runbooks API + adapters + testes
│   ├── packs/devsecops/            120 runbooks DevSecOps + adapters + testes
│   ├── packs/ai-mcp/               100 runbooks IA/MCP + adapters + testes
│   ├── bindings/labs.yaml          ligação canónica pack ↔ campanha ↔ laboratório
│   ├── catalog/                    catálogos derivados (gerados, não canónicos)
│   ├── docs/                       arquitetura da camada security
│   ├── tools/securityctl.py        CLI unificado de validação e catálogo
│   └── tests/                      testes transversais do monorepo
│
├── kali-mcp/                       imagem, Compose e scripts do Kali MCP
│   ├── config/                     configuração do servidor MCP
│   ├── scripts/                    utilitários de lifecycle da imagem
│   └── data/results/               resultados locais — ignorados por Git
│
├── deployment/                     deployment tracking e drift detection
│   ├── deployment_tracking.py      implementação canónica
│   ├── deploy.sh verify.sh
│   │   drift-check.sh rollback.sh  wrappers com lock exclusivo
│   └── tests/                      testes do módulo de deployment
│
├── skills/                         instruções operacionais do agente Hermes
├── config/                         configuração local não sensível
└── .github/workflows/              CI: validate, security, publicações GHCR
```

## Função de cada componente

| Componente | Função | Fonte de verdade |
| --- | --- | --- |
| `platform/environments/**` | define cada laboratório: origem, versão, recursos, runtime, egress, lifecycle, reset | manifesto YAML |
| `platform/registry.yaml` | runtimes suportados e estado de descoberta | ficheiro |
| `platform/rollout.yaml` | ordem faseada de instalação | ficheiro |
| `platform/scripts/labctl.py` | CLI read-only de catálogo/rollout; **não** inicia nem destrói | código |
| `platform/scripts/lab-*.sh` | wrappers de lifecycle (list/status/validate/plan/start/stop/reset/destroy) | código |
| `security/packs/<domain>/runbooks` | definição determinística dos testes | YAML |
| `security/packs/<domain>/campaigns` | agrupamento ordenado de runbooks | YAML |
| `security/packs/<domain>/adapters` | tradução runbook → pedido tipado ao runner | Python |
| `security/bindings/labs.yaml` | única ligação autorizada entre `security/` e `platform/` | YAML |
| `security/tools/securityctl.py` | validação transversal e geração de catálogo | código |
| `kali-mcp/` | execution plane atual: 12 ferramentas por STDIO | imagem + config |
| `deployment/` | integridade de configuração aplicada vs. commit | código + estado |
| `roadmap/` + `docs/roadmap` | intenção futura; não descreve estado implementado | YAML + Markdown |

## Fonte de verdade canónica

1. **Git** é a fonte de verdade de código, manifestos, runbooks, campanhas,
   políticas, schemas, documentação e workflows.
2. **YAML é canónico**; JSON e CSV derivados são descartáveis.
3. **GHCR** guarda imagens construídas pelo projeto; o runtime consome apenas
   digests aceites.
4. Em divergência entre uma issue do GitHub e o repositório, **prevalece o
   repositório**.

## Estado local, evidência e artefactos ignorados

Nada disto é versionado (ver `.gitignore`):

| Caminho | Conteúdo |
| --- | --- |
| `.deployment.json` | estado de deployment; modo `0600`; só inventário sha256/tamanho/modo |
| `.deployment-snapshots/` | snapshots de rollback por `deployment_id` |
| `.runtime/` | Compose efetivo e estado transitório de laboratórios |
| `kali-mcp/data/results/` | resultados de execução |
| `evidence/raw/`, `state/`, `runtime/` | evidência bruta e estado |
| `security/catalog/generated*.json` | catálogos derivados |
| `*.log`, `*.db`, `*.sqlite`, `*.tar*`, `*.zip` | artefactos locais |
| `.env`, `*.key`, `*.pem`, `*.token`, `*.secret` | material sensível — **nunca** comitar |

Evidência partilhável é sanitizada e guardada **fora do Git**.

## O que nunca deve ser editado diretamente

- **`main`** — só por PR com CI verde.
- **`.deployment.json` e `.deployment-snapshots/`** — só através de
  `deployment/deploy.sh` e `deployment/rollback.sh`.
- **`.runtime/`** — gerado pelo lifecycle; editar à mão provoca drift e cleanup
  degradado.
- **`security/catalog/generated*.json`** — derivado de `securityctl catalog`.
- **Ficheiros dentro de containers em execução** — o container é descartável; a
  alteração pertence ao manifesto.
- **Packages GHCR já aceites** — não retaguear, não apagar, não mudar visibilidade
  (ver [transição privada](ghcr-private-readonly-transition.md)).

## Clones e worktrees

O clone canónico neste host é `/home/estourpm/hermes-labs/hermes-security-labs`.
Clones antigos ou worktrees temporárias não são fonte de verdade e não devem
receber commits. Confirme sempre antes de trabalhar:

```bash
git rev-parse --show-toplevel
git status --porcelain
```

## Ver também

- [Architecture](architecture.md)
- [Operator guide](operator-guide.md)
- [Contributor guide](contributor-guide.md)
