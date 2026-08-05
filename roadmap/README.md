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
| [`epics/security-validation-platform-v2.yaml`](epics/security-validation-platform-v2.yaml) | Backlog machine-readable |
| [`../schemas/backlog-epic.schema.json`](../schemas/backlog-epic.schema.json) | Schema de validação do backlog |
| [`tests/test_backlog.py`](tests/test_backlog.py) | Testes de integridade do backlog |

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
