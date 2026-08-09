# Maturidade do catálogo de laboratórios

Este documento define o que significa um laboratório ser reprodutível neste
repositório, como a maturidade é medida, e qual é a fila objetiva de promoção a
`production-ready`. É a referência de onboarding para quem adiciona um lab novo.

A medição é feita pelo auditor read-only `platform/scripts/lab_audit.py`. O
auditor nunca arranca, pára ou toca em runtimes: lê manifests, `compose.yaml` e
os scripts de ciclo de vida presentes em Git.

## Duas populações distintas

O catálogo tem 57 entradas, mas só uma minoria tem ativos de runtime versionados.
Confundir as duas populações é a principal causa de expectativas erradas.

| População | Definição | Garantias |
| --- | --- | --- |
| `runtime-managed` | diretório com `manifest.yaml` **e** `compose.yaml` | ciclo de vida, isolamento e determinismo auditados |
| `catalog-only` | manifest YAML plano, sem ativos de runtime no repositório | apenas metadados de catálogo; sem garantias de lifecycle |

Um lab `catalog-only` com `status: CURRENT` descreve intenção e enquadramento,
não uma capacidade executável a partir deste repositório.

## Contrato de reprodutibilidade (`runtime-managed`)

| Dimensão | Regra | Severidade |
| --- | --- | --- |
| Ciclo de vida | `start.sh`, `stop.sh`, `destroy.sh` presentes | fatal |
| Ciclo de vida | `reset.sh`, `status.sh`, `smoke.sh` presentes | aviso |
| Conectividade Kali | `connect-kali.sh` e `disconnect-kali.sh` presentes | aviso |
| Determinismo | cada imagem fixada por `@sha256:` | aviso |
| Healthcheck | cada serviço com imagem declara `healthcheck` | aviso |
| Exposição | cada porta publicada liga a `127.0.0.1` | fatal |
| Exposição | porta de host parametrizável `${VAR:-default}` | aviso |
| Isolamento | labs multi-serviço declaram rede `internal: true` | aviso |

Veredictos: `PASS` (sem achados), `DEGRADED` (só avisos), `FAIL` (pelo menos um
achado fatal), `CATALOG-ONLY` (fora do contrato).

## Utilização

```bash
python3 platform/scripts/lab_audit.py audit --runtime-managed
python3 platform/scripts/lab_audit.py audit --json
python3 platform/scripts/lab_audit.py baseline-check
```

`platform/lab-audit-baseline.yaml` regista o veredicto aceite por ambiente. O
workflow `validate` corre `audit --strict` e `baseline-check`, por isso qualquer
regressão de maturidade — ou qualquer melhoria não registada — parte o CI. Ao
mudar um lab, atualize o baseline no mesmo PR: é uma decisão explícita, não um
efeito lateral.

## Estado atual (`runtime-managed`)

| Ambiente | Veredicto | Lacuna dominante |
| --- | --- | --- |
| dvwa | PASS | — |
| dvapi | PASS | — |
| graphql-vulnerable-lab | PASS | — |
| nodegoat | PASS | — |
| pygoat | PASS | — |
| vampi | PASS | — |
| webgoat | PASS | — |
| wrongsecrets | PASS | — |
| crapi | PASS | — |
| juice-shop | DEGRADED | porta de host fixa; sem scripts Kali |

## Fila de promoção a production-ready

O critério de promoção é `PASS` no auditor **mais** evidência de execução real
do ciclo de vida num host autorizado. O auditor cobre a primeira metade; a
segunda continua a ser trabalho de aceitação com execução.

1. **Prontos para aceitação de runtime** — `dvwa`, `dvapi`, `vampi`,
   `graphql-vulnerable-lab`, `nodegoat`, `webgoat`, `wrongsecrets`, `pygoat`,
   `crapi`. Já cumprem o contrato declarativo; falta apenas registar a execução
   observada.
2. **Uma correção pequena de distância** — `juice-shop`: parametrizar a porta de
   host e adicionar os scripts `connect-kali.sh` / `disconnect-kali.sh`.

Ambientes `catalog-only` não entram nesta fila enquanto não trouxerem
`compose.yaml` e scripts de ciclo de vida para o repositório.

## Contrato de ambiente (executáveis vs catálogo)

`platform/schemas/lab-manifest.schema.json` distingue duas populações através de
`execution_class`:

- `executable`: labs com runtime real no repositório (`manifest.yaml` + `compose.yaml`
  ou fixture kind). Têm de declarar `schema_version: "1.1"`, `backend`,
  `authorization_state`, `network` (ingress com `scope`/`bindings` e egress
  `default: deny` com allowlist ou perfil), `resources`, `liveness`, `readiness`
  (`probe`, `timeout_seconds`, `success_criteria`), `reset_strategy`, `persistence`
  (retenção de evidência) e `lifecycle`. Falta de qualquer um destes campos é erro de
  validação: fail-closed, sem defaults implícitos.
- `catalog-only` (ou ausente): entradas YAML planas que declaram intenção. Não são
  validadas contra o contrato executável e não podem ser tratadas como executáveis.

`authorization_state` aceita `LAB_ONLY`, `AUTHORIZED_TEST_TARGET`, `UNVERIFIED`,
`BLOCKED` e `EXTERNAL`; apenas os dois primeiros são consideradas execução autorizada.
Quando `network.egress.enforced` é `false` (bridge de publicação com saída possível),
`residual_risk` é obrigatório.

Validar com `python3 platform/scripts/labctl.py validate`; o contrato negativo está
coberto por `platform/tests/test_environment_contract.py`.

## Adicionar um lab novo

1. Criar `platform/environments/<categoria>/<lab>/manifest.yaml` conforme
   `platform/schemas/lab-manifest.schema.json`.
2. Adicionar `compose.yaml` com imagens fixadas por digest, healthchecks,
   publicação apenas em `127.0.0.1` com porta parametrizável, e rede
   `internal: true` para os serviços de suporte.
3. Adicionar os scripts de ciclo de vida em `scripts/`.
4. Correr `python3 platform/scripts/lab_audit.py audit --runtime-managed` e
   resolver os achados até `PASS`.
5. Registar o veredicto em `platform/lab-audit-baseline.yaml`.

Documentos relacionados: [Operator guide](operator-guide.md),
[Contributor guide](contributor-guide.md), [Security model](security-model.md).
