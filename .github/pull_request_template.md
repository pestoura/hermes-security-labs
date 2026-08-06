# Summary

-

## Scope

- Issues:
- Type: feat / fix / docs / test / ci

## Validation

- [ ] `python security/tools/securityctl.py validate` (150/120/100/370, warnings=0)
- [ ] testes por diretório relevantes (`deployment/tests`, `roadmap/tests`,
      `security/tests`, `docs/tests`, packs afetados)
- [ ] `ruff check .`
- [ ] `bash -n` nos scripts alterados
- [ ] `git diff --check` e árvore limpa

## Documentation

- [ ] documentação afetada atualizada nesta PR
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
