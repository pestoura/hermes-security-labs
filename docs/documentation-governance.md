# Documentation governance

## Owner e fonte de verdade

- O proprietário do repositório é o owner da documentação.
- A documentação vive em Git e é a fonte de verdade. Issues do GitHub são uma vista
  de trabalho; em divergência prevalece o repositório.
- A navegação canónica é [`docs/README.md`](README.md), ligada a partir do
  [README principal](../README.md). Documento novo que não esteja ligado a partir da
  navegação não é considerado publicado.
- Cada documento canónico tem um âmbito único. Conteúdo repetido deve ser
  substituído por uma ligação relativa.

## Documentos canónicos

| Documento | Âmbito |
| --- | --- |
| [`project-overview.md`](project-overview.md) | propósito, limites, estado atual vs. roadmap |
| [`repository-tour.md`](repository-tour.md) | estrutura, fonte de verdade, artefactos ignorados |
| [`architecture.md`](architecture.md) | planos, fluxo de execução, diagramas, boundaries |
| [`getting-started.md`](getting-started.md) | onboarding e validação local |
| [`operator-guide.md`](operator-guide.md) | operação diária e recuperação |
| [`contributor-guide.md`](contributor-guide.md) | como contribuir e o que testar |
| [`troubleshooting.md`](troubleshooting.md) | sintomas, diagnóstico, ação |
| [`security-model.md`](security-model.md) | autorização, isolamento, redaction, proibições |
| [`glossary-and-references.md`](glossary-and-references.md) | termos e frameworks |
| [`documentation-governance.md`](documentation-governance.md) | este documento |

## Versionamento

- A documentação segue o commit. Não há versões paralelas.
- Alterações relevantes de contrato entram no [CHANGELOG](../CHANGELOG.md).
- Estado futuro é sempre marcado explicitamente como **roadmap** e referenciado ao
  ID `SVP2-<pilar>-<NN>` correspondente. É proibido descrever funcionalidade
  inexistente como implementada.

## Revisão de links e diagramas

Os testes em `docs/tests/` verificam automaticamente:

- existência dos documentos canónicos;
- referência a partir do README principal e da navegação;
- ligações relativas Markdown resolvíveis no repositório;
- fences Mermaid fechados e de tipo suportado pelo GitHub
  (`flowchart`, `graph`, `sequenceDiagram`, `stateDiagram-v2`, `classDiagram`,
  `erDiagram`, `journey`, `gantt`, `pie`, `mindmap`, `timeline`, `flowchart TD/LR`);
- que comandos documentados que referem caminhos do repositório apontam para
  caminhos existentes.

Executar localmente:

```bash
python3 -m pytest -q docs/tests -p no:cacheprovider
```

Verificação manual complementar: abrir o documento no GitHub e confirmar que cada
diagrama renderiza. Um bloco Mermaid que não renderiza conta como documentação
partida.

## Atualizar documentação quando contratos mudam

Alteração de contrato exige atualização de documentação **na mesma PR**:

| Alteração | Documento a atualizar |
| --- | --- |
| novo laboratório ou manifesto | [`repository-tour.md`](repository-tour.md), [`contributor-guide.md`](contributor-guide.md) |
| novo runbook, pack ou contagem | [`project-overview.md`](project-overview.md) (tabela dos 370) |
| novo binding ou campanha | [`contributor-guide.md`](contributor-guide.md) |
| alteração de lifecycle ou de estados | [`architecture.md`](architecture.md), [`operator-guide.md`](operator-guide.md) |
| alteração de deployment/drift | [`deployment-tracking.md`](deployment-tracking.md), [`operator-guide.md`](operator-guide.md) |
| alteração de allowlist, rede ou redaction | [`security-model.md`](security-model.md) |
| novo modo de falha observado | [`troubleshooting.md`](troubleshooting.md) |
| novo framework ou sigla | [`glossary-and-references.md`](glossary-and-references.md) |
| alteração de fases ou pilares | [`roadmap/security-validation-platform-v2.md`](roadmap/security-validation-platform-v2.md) e `roadmap/epics/` |
| trabalho numa umbrella epic `SVP2-*` | documento(s) de concept epic em [`roadmap/epics/`](roadmap/epics/) — secções 14 e 15 |

## Concept epics e ciclo de vida documental

As 45 concept epics (`EPIC-01`…`EPIC-45`) documentam a intenção de desenho; as 21 umbrella
epics `SVP2-*` (issues #76–#96) continuam a ser as unidades de entrega. Ver
[epic catalogue](roadmap/epic-catalogue-45.md).

O contrato Intent → As-Built → Final está em
[`architecture/architecture-documentation-lifecycle.md`](architecture/architecture-documentation-lifecycle.md)
e é obrigatório:

- ao iniciar trabalho numa umbrella, o estado da concept epic passa a `IMPLEMENTING`;
- cada PR que altere comportamento coberto atualiza a secção 14 na mesma PR;
- decisões materiais exigem ADR;
- **nenhuma umbrella pode ser fechada com a secção 15 (as-built) por preencher** em qualquer
  concept epic que cubra;
- divergências entre intenção e implementação são registadas, não apagadas.

## Checklist de documentação em PRs

Incluir na descrição da PR:

- [ ] a documentação afetada foi atualizada na mesma PR;
- [ ] documentos novos estão ligados a partir de `docs/README.md`;
- [ ] ligações relativas verificadas (`pytest -q docs/tests`);
- [ ] diagramas Mermaid renderizam no GitHub;
- [ ] funcionalidade futura marcada como **roadmap** com o ID `SVP2-*`;
- [ ] se a PR toca trabalho de uma umbrella `SVP2-*`, o documento da concept epic
      correspondente foi atualizado (secção 14, e secção 15 quando a umbrella fecha);
- [ ] sem credenciais, tokens, payloads ofensivos ou instruções contra alvos
      externos;
- [ ] exemplos de comandos apontam para caminhos existentes.

## Ver também

- [Contributor guide](contributor-guide.md)
- [Documentação — índice](README.md)
