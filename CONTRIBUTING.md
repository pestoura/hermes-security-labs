# Contributing

O guia completo é [`docs/contributor-guide.md`](docs/contributor-guide.md). Este
ficheiro é o resumo de entrada.

## Antes de começar

- Ler [Quickstart](docs/quickstart.md) e validar o repositório localmente.
- Confirmar que trabalha no clone canónico e com a árvore limpa (`git status --porcelain`).
- Procurar duplicação antes de criar seja o que for
  (`securityctl.py list`, `labctl.py list`).

## Regras invioláveis

- Nunca enviar segredos, tokens, cookies, cabeçalhos de autorização ou evidência bruta.
- Nunca escrever diretamente em `main`.
- Nenhum alvo fora de um laboratório registado.
- Sem alteração de allowlist, egress ou visibilidade de packages sem autorização explícita.
- Imagens consumidas por digest imutável; nunca `latest` nem tags móveis.

## Branch, commit e PR

```text
issue → branch → commit → pull request → CI → revisão → squash merge → branch apagada
```

- Uma branch por objetivo, prefixada: `docs/…`, `fix/…`, `feat/…`, `test/…`, `ci/…`.
- Commits com prefixo convencional (`feat`, `fix`, `docs`, `test`, `ci`).
- `Closes` apenas em issues integralmente concluídas; nunca em umbrella epics parciais.
- Usar o [template de PR](.github/pull_request_template.md) e preencher todos os checkboxes
  aplicáveis com resultado factual.

## Gates antes de abrir PR

```bash
python3 platform/scripts/labctl.py validate
python3 platform/scripts/lab_audit.py audit --strict
python3 platform/scripts/lab_audit.py baseline-check
python3 security/tools/securityctl.py validate          # 150/120/100/370, warnings=0
python3 -m pytest -q docs/tests       -p no:cacheprovider
python3 -m pytest -q deployment/tests -p no:cacheprovider
python3 -m pytest -q roadmap/tests    -p no:cacheprovider
python3 -m pytest -q security/tests   -p no:cacheprovider
python3 -m pytest -q platform/tests   -p no:cacheprovider
make lint                                               # gate de lint do CI
git ls-files '*.sh' | xargs -r -n1 bash -n
git diff --check
```

`pytest` na raiz sem argumentos **não** é um gate válido: existem colisões de nomes de
teste entre packs. O CI corre por diretório e é esse o contrato.

Falhas pré-existentes conhecidas neste host: quatro *drills* de kill switch em
`platform/tests` (`test_kill_switch_*_subprocess_drill.py`) falham com
`ConformanceError: candidate closed stdout without a response`, tanto em `main` como
em qualquer branch. Confirme com `git stash -u` + execução em `main` antes de atribuir
a falha à sua alteração; medir sempre o *delta* entre base e branch.

## Reportar problemas

Usar o [issue template](.github/ISSUE_TEMPLATE/bug_report.md). Incluir comando exato,
saída observada, saída esperada e commit (`git log --oneline -1`).
