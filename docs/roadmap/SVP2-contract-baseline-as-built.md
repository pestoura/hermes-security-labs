# Security Validation Platform v2 — AS_BUILT do baseline contratual

## Estado da entrega

**Baseline do repositório:** `COMPLETE`

**Promoção para produção:** `BLOCKED`

**Alteração de runtime nesta entrega:** `NO_RUNTIME_CHANGE`

Este documento consolida a implementação do backlog `Security Validation Platform v2` no repositório `hermes-security-labs`. A palavra **complete** aplica-se ao baseline contratual, aos schemas, às decisões fail-closed, aos testes e à integração no repositório. Não significa que os runtimes, feeds, clouds, laboratórios, dispositivos ou integrações externas tenham sido executados em produção.

A fonte canónica de estado continua a ser `roadmap/epics/security-validation-platform-v2.yaml`.

## Princípio de reconciliação

Um epic só é marcado `completed` quando os seus critérios de aceitação podem ser integralmente demonstrados com evidência presente no repositório. Um epic com contrato implementado mas com critérios que dependem de runtime, integração externa ou observação real permanece `implementing`.

Por esta razão, esta entrega não converte `NOT_RUN` ou `NOT_IMPLEMENTED` em sucesso implícito.

## Estado canónico

| Epic | Estado | Evidência principal | Motivo para permanecer aberto quando aplicável |
| --- | --- | --- | --- |
| SVP2-A-01 | completed | baseline arquitetural já integrado | critérios arquiteturais concluídos |
| SVP2-A-02 | implementing | PRs #133 e #134 | assinatura/trust store, enforcement no gateway e kill switch de runtime ainda não demonstrados |
| SVP2-A-03 | completed | PR #135 | governação, DoR/DoD e releases demonstrados no repositório |
| SVP2-B-01 | implementing | PRs #136 e #137 | integração Kali MCP e deployment do gateway continuam `NOT_RUN` |
| SVP2-B-02 | implementing | PRs #129, #131 e #132, além dos blocos anteriores do EPIC-05 | evidência permanece baseada em fixed synthetic workers; produção `NOT_RUN`, sandbox `NOT_IMPLEMENTED` |
| SVP2-B-03 | implementing | PRs #139 e #140 | Docker/network enforcement, prova real de zero resíduo e orphan detector ainda não demonstrados |
| SVP2-C-01 | implementing | PR #142 | imagem real, non-root/read-only/capabilities em runtime continuam `NOT_RUN` |
| SVP2-C-02 | implementing | PR #143 | geração SBOM, assinatura, provenance, scanning e promoção real continuam `NOT_RUN` |
| SVP2-D-01 | implementing | PR #141 | storage, cifragem, imutabilidade, retenção e replay de produção continuam `NOT_RUN`/`NOT_IMPLEMENTED` |
| SVP2-D-02 | implementing | PR #144 | OpenTelemetry, readiness real, chaos e maturidade de produção continuam `NOT_RUN` |
| SVP2-E-01 | implementing | PR #146 | sync externo e graph store continuam `NOT_RUN`/`NOT_IMPLEMENTED` |
| SVP2-E-02 | implementing | PR #148 | HTTP API, database, graph query engine e planner de produção continuam `NOT_IMPLEMENTED`/`NOT_RUN` |
| SVP2-F-01 | implementing | PR #150 | adversary emulation e Attack Flow transport continuam `NOT_RUN`/`NOT_IMPLEMENTED` |
| SVP2-F-02 | implementing | PR #153 | telemetria defensiva, SIEM/EDR, containment e exercícios reais continuam por integrar |
| SVP2-G-01 | implementing | PR #151 | provider registry de produção e execução de validadores externos continuam `NOT_IMPLEMENTED`/`NOT_RUN` |
| SVP2-H-01 | implementing | PR #152 | source sync, geração, labs, image build, detections e autonomous merge continuam `NOT_RUN` |
| SVP2-I-01 | implementing | PR #154 | reset determinístico e cleanup proof ainda não foram observados em runtimes reais |
| SVP2-J-01 | completed | PR #155 | critérios de scoring auditável e lifecycle/regressão integralmente demonstrados por contrato e testes |
| SVP2-J-02 | implementing | PR #157 | schemas oficiais não são embebidos/fetched; signing criptográfico e entrega externa continuam `NOT_RUN` |
| SVP2-K-01 | implementing | PR #147 | verificação de assinatura, loading, isolamento e certificação de extensões em produção continuam `NOT_RUN` |
| SVP2-L-01 | implementing | PR #156 | Kubernetes, AD/identity, cloud, mobile e IoT/OT/hardware continuam `NOT_RUN`; cleanup real é pré-condição de ativação |

## Baseline entregue

A implementação atual contém contratos e testes para:

- Rules of Engagement as Code e intrusividade L0-L4;
- gateway de execução tipado e recusa de execução arbitrária;
- Runner Protocol v2, correlação, idempotência, cancelamento e erros normalizados;
- lifecycle transacional de laboratórios, egress default-deny e zero-residue proof;
- runtime base non-root e política de capabilities;
- capability registry e gates de supply chain;
- Evidence Plane v2, redaction lineage e replay descriptor;
- observabilidade/readiness/failure suite e maturidade M0-M5;
- Security Knowledge Fabric, proveniência, conflitos e precedência;
- Security Knowledge API, snapshots e propostas não executáveis;
- threat profiles, adversary-emulation plans não executáveis e attack graph;
- purple-team outcomes, D3FEND e exercícios de resiliência como planos;
- resolução de vulnerabilidades e validation-provider trust;
- continuous content promotion e anti-degradation gates;
- Lab Schema v2, Registry, isolamento, TTL e reset fingerprint;
- risk scoring auditável e finding lifecycle;
- interoperabilidade OSCAL/CACAO/Attack Flow com validação contra schema alvo explícito;
- extension SDK/conformance/certification contract;
- constraints de expansão Kubernetes, identity, cloud, mobile e IoT/OT.

## Gates de integração

A última composição técnica antes desta reconciliação foi `main` no commit `230aa0531b3a04ea93ac7655a49279d0958935e4`.

Foram observados com sucesso:

- validação de documentação e YAML;
- catálogo e source of truth de runtime;
- Runner Protocol v2 e conformance kit;
- API, DevSecOps e AI/MCP packs;
- monorepo integration;
- lifecycle e source-archive tests;
- roadmap/backlog/governance tests;
- Ruff;
- Gitleaks.

As gates da presente PR de reconciliação continuam autoritativas para a entrega deste documento e da atualização de estados.

## Bloqueios para promoção de produção

A próxima fase deixa de ser desenho contratual e passa a ser **operacionalização controlada**. Os principais blocos de promoção são:

1. integrar RoE, gateway e Runner Protocol nos runtimes reais do Hermes/Kali MCP;
2. demonstrar isolamento, cleanup, egress e orphan detection contra recursos reais descartáveis;
3. construir e validar imagens non-root com SBOM, assinatura, provenance e scanning;
4. implementar Evidence Plane persistente com cifragem, retenção e replay controlado;
5. ligar OpenTelemetry/readiness e executar a failure suite em ambiente isolado;
6. implementar sync/API/storage reais do Security Knowledge Fabric;
7. ligar telemetria defensiva para purple-team outcomes;
8. executar factories e Lab Registry contra laboratórios descartáveis;
9. validar interoperabilidade contra schemas oficiais versionados e assinatura criptográfica real;
10. certificar extensões reais e, só depois, ativar Kubernetes/identity/cloud/mobile/IoT-OT por domínio.

Cada um destes passos mantém os requisitos existentes de autorização formal, âmbito explícito, allowlists, kill switch, limites de recursos, evidência e Human-in-the-Loop.

## Decisão de entrega

**Decisão:** aceitar o repositório como baseline contratual integrado da Security Validation Platform v2.

**Risco aceite:** nenhum estado `NOT_RUN`/`NOT_IMPLEMENTED` é considerado demonstrado.

**Impacto:** o roadmap deixa de ter epics em `proposed`; o trabalho remanescente é execução e integração operacional dos contratos já definidos.

**Estado:** `AS_BUILT — CONTRACT BASELINE COMPLETE / PRODUCTION PROMOTION BLOCKED`.
