# Summary

-

## Scope

- Issues:
- Type: feat / fix / docs / test / ci

## Validation

- [ ] `make validate` (catálogo, `lab_audit --strict`, `baseline-check`,
      securityctl 150/120/100/370 warnings=0, sintaxe shell)
- [ ] testes por diretório relevantes (`docs/tests`, `deployment/tests`,
      `roadmap/tests`, `platform/tests`, `security/tests`, packs afetados)
- [ ] `make lint` (gate de lint do CI; `ruff check .` nu não é o gate)
- [ ] `git diff --check` e árvore limpa
- [ ] falhas pré-existentes distinguidas das novas (delta base vs branch)

## Documentation

- [ ] documentação afetada atualizada nesta PR
- [ ] se a PR muda comandos de operação, [`docs/quickstart.md`](../docs/quickstart.md)
      reflete o comportamento real
- [ ] documentos novos ligados a partir de [`docs/README.md`](../docs/README.md)
- [ ] diagramas Mermaid renderizam no GitHub
- [ ] funcionalidade futura marcada como **roadmap** com o ID `SVP2-*`
- [ ] documento da concept epic (`docs/roadmap/epics/EPIC-NN-*.md`) atualizado quando
      a PR toca trabalho de uma umbrella `SVP2-*`: secção 14 sempre, secção 15
      (as-built) obrigatória antes de fechar a umbrella

## Security

- [ ] sem segredos, tokens, cookies ou evidência bruta
- [ ] sem alvos fora de laboratórios registados
- [ ] sem alteração de allowlist, egress ou visibilidade de packages sem
      autorização explícita
