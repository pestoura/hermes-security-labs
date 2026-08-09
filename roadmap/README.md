# Roadmap and backlog

Backlog versionado da **Security Validation Platform v2**.

## Fontes canónicas

| Caminho | Conteúdo |
| --- | --- |
| [`../docs/roadmap/security-validation-platform-v2.md`](../docs/roadmap/security-validation-platform-v2.md) | Visão, princípios, fases, riscos, Definition of Ready/Done e releases |
| [`../docs/roadmap/current-walking-skeleton-status.md`](../docs/roadmap/current-walking-skeleton-status.md) | Estado reconciliado do walking skeleton, separando prova repo/CI de aceitação live Hermes/runtime |
| [`governance.yaml`](governance.yaml) | Taxonomia verificável, DoR/DoD, funções críticas, objetivos de resiliência e releases |
| [`epics/security-validation-platform-v2.yaml`](epics/security-validation-platform-v2.yaml) | Backlog machine-readable das 21 umbrella epics |
| [`epics/security-validation-platform-v2-concepts.yaml`](epics/security-validation-platform-v2-concepts.yaml) | Catálogo machine-readable das 45 concept epics |
| [`../docs/roadmap/epic-catalogue-45.md`](../docs/roadmap/epic-catalogue-45.md) | Catálogo mestre 45 concept epics e mapping 45→21 |
| [`../docs/roadmap/epics/`](../docs/roadmap/epics/) | Um documento por concept epic (`EPIC-01`…`EPIC-45`) |
| [`../docs/architecture/security-validation-reference-architecture.md`](../docs/architecture/security-validation-reference-architecture.md) | Arquitetura de referência |
| [`../docs/architecture/architecture-documentation-lifecycle.md`](../docs/architecture/architecture-documentation-lifecycle.md) | Contrato Intent → Implementing → As-Built → Final |
| [`../schemas/backlog-epic.schema.json`](../schemas/backlog-epic.schema.json) | Schema do backlog |
| [`../schemas/roadmap-governance.schema.json`](../schemas/roadmap-governance.schema.json) | Schema da política de governação |
| [`tests/test_backlog.py`](tests/test_backlog.py) | Integridade estrutural e dependências do backlog |
| [`tests/test_governance.py`](tests/test_governance.py) | Taxonomia, DoR/DoD, resiliência e cobertura de releases |

## Duas camadas: 45 conceitos, 21 entregas

- **45 concept epics** (`EPIC-01`…`EPIC-45`): espaço de desenho, um documento cada.
- **21 umbrella epics** (`SVP2-<pilar>-<NN>`, issues #76–#96): unidades de entrega, planeamento, evidência e fecho.

Cada concept epic mapeia para exatamente uma umbrella. As concept epics nunca substituem as umbrellas como unidade de entrega.

## Fonte de verdade e precedência

1. O backlog e a governação machine-readable são canónicos para IDs, estados, dependências, labels e releases.
2. Os documentos em `docs/` são canónicos para intenção, arquitetura, decisões, evidência e limitações.
3. As issues GitHub são a vista operacional e devem ser reconciliadas com o repositório.
4. Em caso de divergência, a alteração é bloqueada até as fontes canónicas serem reconciliadas; não existe correção silenciosa.

## Taxonomia de labels

Cada umbrella epic tem exatamente:

- `roadmap` e `architecture`;
- uma label `pillar:A..L`;
- uma label `priority:P0..P3`;
- uma label `status:proposed|implementing|completed`;
- uma label `type:epic`;
- no máximo uma `impact:L0..L4`;
- no máximo uma `runtime:<perfil>`.

Labels duplicadas, dimensões múltiplas e labels simples desconhecidas são recusadas pelos testes.

## Definition of Ready

Um epic só passa a `implementing` quando cada critério `DOR-*` aplicável em [`governance.yaml`](governance.yaml) possui evidência verificável. Para trabalho executável são obrigatórios autorização, âmbito, janela, stop conditions e plano de evidência. Para alterações de runtime são obrigatórios failure modes e rollback.

Ausência de evidência não é interpretada como Ready.

## Definition of Done

Um epic só passa a `completed` quando cada critério `DOD-*` aplicável possui evidência, incluindo:

- merge identificável no `main`;
- gates de repositório, segurança e Gitleaks verdes no head final;
- validação pós-merge verde;
- testes positivos, negativos, adversariais e de regressão proporcionais ao risco;
- documentação canónica e limitações atualizadas;
- evidência sanitizada e ausência de segredos;
- rollback demonstrado ou declaração `NO_RUNTIME_CHANGE`;
- issue e backlog reconciliados.

`FINAL` é proibido enquanto qualquer critério de produção obrigatório estiver `NOT_RUN` ou `NOT_IMPLEMENTED`.

## Funções críticas e resiliência

A política identifica cinco funções críticas: autorização, emergency stop, cadeia de custódia, cleanup transacional e consistência da fonte canónica. Cada função tem failure policy, degraded mode e um objetivo mensurável. Estados `planned`, `partial` e `demonstrated_*` distinguem objetivos de evidência já comprovada.

## Releases

As releases `v2.0` a `v2.4` cobrem todos os 21 umbrella epics exatamente uma vez. Cada release tem fases, milestone, epics e critérios de saída. Uma release não é promovida com gates obrigatórias pendentes, sem rollback de runtime ou com alegações finais não comprovadas.

## Validação local

```bash
python -m pytest -q roadmap/tests -p no:cacheprovider
```

## Âmbito

Este modelo é documentação, schema e validação de governação. Não altera runtimes, containers, serviços nem introduz automações ou jobs agendados. `NO_RUNTIME_CHANGE`.
