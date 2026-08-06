# Roadmap and backlog

Backlog versionado da **Security Validation Platform v2**.

## Ficheiros

| Caminho | Conteúdo |
| --- | --- |
| [`../docs/roadmap/security-validation-platform-v2.md`](../docs/roadmap/security-validation-platform-v2.md) | Visão, princípios, fases, riscos, DoR/DoD e releases |
| [`../docs/architecture/security-validation-reference-architecture.md`](../docs/architecture/security-validation-reference-architecture.md) | Arquitetura de referência |
| [`../docs/architecture/framework-crosswalk.md`](../docs/architecture/framework-crosswalk.md) | Crosswalk de frameworks e níveis de confiança |
| [`../docs/architecture/security-knowledge-fabric.md`](../docs/architecture/security-knowledge-fabric.md) | Grafo de conhecimento e sync de fontes |
| [`../docs/architecture/continuous-content-factories.md`](../docs/architecture/continuous-content-factories.md) | Fábricas de conteúdo e lifecycle de promoção |
| [`epics/security-validation-platform-v2.yaml`](epics/security-validation-platform-v2.yaml) | Backlog machine-readable das 21 umbrella epics (unidades de entrega) |
| [`epics/security-validation-platform-v2-concepts.yaml`](epics/security-validation-platform-v2-concepts.yaml) | Catálogo machine-readable das 45 concept epics (intenção de desenho) |
| [`../docs/roadmap/epic-catalogue-45.md`](../docs/roadmap/epic-catalogue-45.md) | Catálogo mestre 45 concept epics e mapping 45→21 |
| [`../docs/roadmap/epics/`](../docs/roadmap/epics/) | Um documento por concept epic (`EPIC-01`…`EPIC-45`) |
| [`../docs/architecture/security-validation-platform-v2-intent.md`](../docs/architecture/security-validation-platform-v2-intent.md) | Documento de intenção end-to-end |
| [`../docs/architecture/architecture-documentation-lifecycle.md`](../docs/architecture/architecture-documentation-lifecycle.md) | Contrato Intent → As-Built → Final |
| [`../schemas/backlog-epic.schema.json`](../schemas/backlog-epic.schema.json) | Schema de validação do backlog |
| [`../schemas/concept-epic.schema.json`](../schemas/concept-epic.schema.json) | Schema do catálogo de concept epics |
| [`tests/test_backlog.py`](tests/test_backlog.py) | Testes de integridade do backlog |
| [`tests/test_concept_catalogue.py`](tests/test_concept_catalogue.py) | Testes de integridade do catálogo 45→21 |

## Duas camadas: 45 conceitos, 21 entregas

- **45 concept epics** (`EPIC-01`…`EPIC-45`): espaço de desenho, um documento cada, estado
  `intent`. Não têm issue GitHub própria.
- **21 umbrella epics** (`SVP2-<pilar>-<NN>`, issues #76–#96): unidades de entrega,
  planeamento e fecho.

Cada concept epic mapeia para exatamente uma umbrella; várias concept epics podem partilhar
a mesma umbrella. As concept epics nunca substituem as umbrellas como unidade de entrega.
Divergências conhecidas entre a discussão conceptual e o YAML de entrega estão registadas em
[epic-catalogue-45.md](../docs/roadmap/epic-catalogue-45.md#2-divergences-between-the-discussion-and-the-current-yaml).

## Fonte de verdade

O YAML e os documentos em `docs/` são canónicos. As issues do GitHub são uma vista de
trabalho e referenciam os IDs `SVP2-<pilar>-<n>`. Em caso de divergência, prevalece o
repositório.

## Convenções

- IDs: `SVP2-A-01` … `SVP2-L-01`; pilares `A`–`L`; fases `0`–`8`.
- Prioridades `P0`–`P3`; esforço `S`/`M`/`L`/`XL`; estado inicial `proposed`.
- Labels: `roadmap`, `architecture`, `pillar:*`, `priority:P0..P3`, `impact:L0..L4`,
  `runtime:*`, `status:proposed`, `type:epic`.

## Validação local

```bash
python -m pytest -q roadmap/tests -p no:cacheprovider
```

## Âmbito

Este backlog é documentação e modelação. Não altera runtimes, containers, serviços nem
introduz automações ou jobs agendados.
