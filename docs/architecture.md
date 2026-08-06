# Architecture

Descrição do sistema tal como está implementado hoje, com o alvo do roadmap v2
identificado explicitamente. Funcionalidades marcadas **roadmap** não existem em
runtime.

## 1. Planos do sistema

- **Control plane — Hermes.** Autorização, seleção de runbooks, planeamento de
  campanha, estado, avaliação dos resultados e reporting. Não executa ferramentas
  ofensivas diretamente e não guarda evidência bruta fora do evidence root.
- **Execution plane — Kali MCP e runners.** Mantém as ferramentas autorizadas
  (12 ferramentas MCP por STDIO, `docker exec -i hermes-kali-mcp`). Executa apenas
  perfis permitidos e nunca decide autorização.
- **Target plane — laboratórios.** Ambientes descartáveis, uma rede por
  laboratório, sem egress por omissão, sem exposição na LAN.
- **Evidence plane.** Resultados normalizados e guardados fora do Git.
- **Source of truth — GitHub.** Código, manifestos, schemas, runbooks e workflows.

### Arquitetura de alto nível

```mermaid
flowchart LR
  subgraph SOT["Source of truth — GitHub"]
    REPO["Repo: manifestos, runbooks, bindings, schemas"]
    GHCR["GHCR: imagens do projeto por digest"]
  end

  subgraph CP["Control plane — Hermes"]
    SEL["Seleção de runbook e campanha"]
    POL["Policy e âmbito autorizado"]
    EVAL["Avaliação fail-safe"]
  end

  subgraph EP["Execution plane"]
    MCP["Kali MCP (STDIO, 12 tools)"]
    RUN["Runners por domínio"]
  end

  subgraph TP["Target plane"]
    LAB["Laboratório isolado (Docker)"]
  end

  subgraph EV["Evidence plane"]
    EVID["Evidência normalizada e sanitizada"]
  end

  REPO --> SEL
  GHCR --> LAB
  SEL --> POL
  POL --> MCP
  MCP --> RUN
  RUN -->|"rede única do laboratório"| LAB
  RUN --> EVID
  EVID --> EVAL
  EVAL --> REPO
```

## 2. Fluxo canónico de execução

```text
runbook → binding → policy → adapter/runner → tool → normalize → evaluate → evidence
```

| Etapa | Responsável | Garantia |
| --- | --- | --- |
| runbook | `security/packs/<domain>/runbooks` | determinístico, sem shell livre |
| binding | `security/bindings/labs.yaml` | o alvo resolve para um laboratório registado |
| policy | `security/packs/<domain>/…/policy.py` | âmbito, risco e deny-by-default |
| adapter | `security/packs/<domain>/adapters` | pedido tipado, sem interpolação arbitrária |
| runner/tool | Kali MCP | apenas ferramentas allowlisted |
| normalize | pack runtime | saída estruturada; erro classificado |
| evaluate | control plane | ausência de sinal nunca produz `secure` |
| evidence | evidence root | sanitizada, fora do Git |

### Sequência de uma campanha

```mermaid
sequenceDiagram
  autonumber
  participant OP as Operador
  participant H as Hermes (control plane)
  participant P as Policy e bindings
  participant L as Lifecycle do laboratório
  participant K as Kali MCP
  participant E as Evidence

  OP->>H: seleciona campanha e laboratório
  H->>P: valida âmbito, alvo e risco
  P-->>H: autorizado ou recusado
  H->>L: provision e readiness do laboratório
  L-->>H: READY
  H->>L: attach do Kali à rede do laboratório
  H->>K: pedido tipado por runbook
  K->>L: executa ferramenta allowlisted
  K-->>H: saída normalizada
  H->>E: escreve evidência sanitizada
  H->>L: detach do Kali
  H->>L: cleanup e prova de zero resíduo
  L-->>H: CLEAN
  H-->>OP: relatório e avaliação
```

## 3. Lifecycle de laboratório

Estados observados pelo lifecycle atual, alinhados com o alvo v2.

```mermaid
stateDiagram-v2
  [*] --> DEFINED
  DEFINED --> PROVISIONING: lab-start
  PROVISIONING --> READY: readiness HTTP/health
  PROVISIONING --> FAILED: timeout ou erro
  READY --> ATTACHED: Kali ligado à rede do lab
  ATTACHED --> RUNNING: execução de runbooks
  RUNNING --> DETACHING: fim da campanha
  DETACHING --> CLEANING: Kali desligado
  CLEANING --> CLEAN: zero containers, redes e volumes
  CLEANING --> QUARANTINED: resíduo não removível
  FAILED --> CLEANING
  CLEAN --> [*]
```

Invariantes:

- uma única rede por laboratório;
- attach/detach decididos por estado real observado, nunca por suposição;
- cleanup idempotente com prova de ausência;
- `QUARANTINED` exige intervenção explícita e não é ignorável.

## 4. Validação de um runbook

```mermaid
flowchart TD
  A["Runbook YAML"] --> B{"Schema válido?"}
  B -- não --> X["Rejeitado: erro de schema"]
  B -- sim --> C{"IDs de alvo resolvem em bindings?"}
  C -- não --> X
  C -- sim --> D{"Shell livre ou payload embebido?"}
  D -- sim --> X
  D -- não --> E["securityctl validate: contagens por domínio"]
  E --> F{"api=150 devsecops=120 ai-mcp=100 warnings=0?"}
  F -- não --> X
  F -- sim --> G["Testes do pack"]
  G --> H{"Controlo positivo e negativo?"}
  H -- não --> I["Permanece experimental"]
  H -- sim --> J["Candidato a calibrado"]
```

## 5. Deployment e drift

O deployment não é um upload: é a prova de que o estado aplicado no host
corresponde a um commit conhecido do repositório.

```mermaid
flowchart LR
  C["Commit em main"] --> D["deploy.sh (lock exclusivo)"]
  D --> S[".deployment.json — inventário sha256/tamanho/modo, 0600"]
  D --> N[".deployment-snapshots/<id> — rollback"]
  S --> V["verify.sh"]
  S --> K["drift-check.sh"]
  V --> R{"Estado"}
  K --> R
  R -->|"tudo coincide"| IS["IN_SYNC"]
  R -->|"ficheiro, modo, runner ou commit divergente"| DD["DRIFT_DETECTED (exit 1)"]
  R -->|"estado ausente, JSON inválido, commit desconhecido, erro"| UK["UNKNOWN (exit 2)"]
  DD --> RB["rollback.sh a partir do snapshot"]
```

Regra fail-safe: ausência de prova, erro ou evidência insuficiente **nunca** produz
`IN_SYNC`.

## 6. Boundaries de confiança e segurança

| Fronteira | Regra |
| --- | --- |
| Control plane → execution plane | apenas pedidos dentro de contrato; o executor não amplia âmbito |
| Execution plane → target plane | apenas a rede do laboratório ativo; sem egress por omissão |
| Target plane → host | sem publicação na LAN; portas apenas em `127.0.0.1` |
| Qualquer plano → evidence | append-only por execução; partilha sempre sanitizada |
| GitHub → Hermes | sem deployment automático, sem self-hosted runner, sem exposição do Docker socket |
| Hermes → GHCR | credencial read-only; consumo por digest imutável |

## 7. Monorepo, runtime, imagem Kali, labs e GitHub

```mermaid
flowchart TB
  GH["GitHub: pestoura/hermes-security-labs"] -->|"PR, CI, merge"| MAIN["main"]
  MAIN -->|"fast-forward"| CLONE["Clone canónico no host Hermes"]
  CLONE -->|"deploy.sh"| STATE[".deployment.json + snapshots"]
  CLONE --> LABDEF["platform/environments/**"]
  LABDEF -->|"compose"| LABS["Laboratórios Docker efémeros"]
  GH -->|"workflow_dispatch"| GHCR["GHCR: imagens do projeto"]
  GHCR -->|"pull por digest"| LABS
  CLONE --> KALICFG["kali-mcp/ (imagem e config)"]
  KALICFG --> KALI["Container hermes-kali-mcp"]
  KALI -->|"attach temporário"| LABS
  KALI --> EVID["Evidência fora do Git"]
```

## 8. Alvo do roadmap v2

```mermaid
flowchart LR
  P0["Fase 0 — Current-base closure"] --> P1["Fase 1 — Arquitetura e Runner Protocol v2"]
  P1 --> P2["Fase 2 — Execução tipada, capability registry, Evidence v2"]
  P2 --> P3["Fase 3 — Image factory"]
  P3 --> P4["Fase 4 — Lifecycle completo e segurança L3/L4"]
  P4 --> P5["Fase 5 — Knowledge fabric"]
  P5 --> P6["Fase 6 — Content factories"]
  P6 --> P7["Fase 7 — Threat-informed, purple team, risco"]
  P7 --> P8["Fase 8 — Domain expansion"]

  subgraph FUT["Fábricas futuras — roadmap, não implementado"]
    RF["Runbook factory"]
    LF["Lab factory"]
    IF["Runtime/image factory"]
    DF["Detection factory"]
  end

  P3 -.-> IF
  P6 -.-> RF
  P6 -.-> LF
  P6 -.-> DF
```

Detalhe canónico em
[reference architecture](architecture/security-validation-reference-architecture.md)
e [roadmap](roadmap/security-validation-platform-v2.md).

## Ver também

- [Security model](security-model.md)
- [Operator guide](operator-guide.md)
- [Arquitetura consolidada da camada security](../security/docs/architecture.md)
