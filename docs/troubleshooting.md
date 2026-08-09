# Troubleshooting

Sintomas frequentes, diagnóstico e ação. A regra transversal é: **ausência de prova
nunca é resultado positivo**.

## Porta de host já em uso

**Sintoma.** `start` aborta com `Port <n> already in use`, ou o Compose falha a
publicar o mapeamento.

**Diagnóstico.**

```bash
ss -ltn | grep -w <porta>
docker ps --format '{{.Names}}\t{{.Ports}}'
```

**Causas conhecidas.** VAmPI publica `5000` por omissão, a mesma porta do servidor
MCP local; DVAPI publica `3000`, a mesma que o Juice Shop.

**Ação.** Definir a variável de porta do ambiente em vez de editar o `compose.yaml`:
`VAMPI_HOST_PORT`, `DVAPI_HOST_PORT`, `PYGOAT_HOST_PORT`, `NODEGOAT_HOST_PORT`,
`GRAPHQL_LAB_HOST_PORT`, `DVWA_HOST_PORT`, `WEBGOAT_HOST_PORT`, `WEBWOLF_HOST_PORT`,
`WRONGSECRETS_HOST_PORT`, `CRAPI_HOST_PORT`. O Juice Shop publica `127.0.0.1:3000`
fixo, sem variável: nesse caso é o outro laboratório que muda de porta.

## `lab-start.sh` não arranca nada

**Sintoma.** `./platform/scripts/lab-start.sh <id>` sai com código `2` e não cria
containers.

**Causa.** Esperado. Os wrappers `lab-{start,stop,reset,destroy}.sh` são
`NOT_IMPLEMENTED`; não existe wrapper genérico de provisionamento.

**Ação.** Usar a interface real do ambiente, tabelada na
[matriz de comandos de lifecycle](quickstart.md#7-matriz-de-comandos-de-lifecycle).

## Runner missing ou hash mismatch

**Sintoma.** `verify.sh` ou `drift-check.sh` reporta runner desatualizado ou
`modified_file` num runner.

**Diagnóstico.**

```bash
bash deployment/verify.sh | head -40
git status --porcelain
git log --oneline -1
```

**Ação.** Se o repositório está correto e o alvo está desatualizado, reaplicar:

```bash
DEPLOY_LOCK_FILE=/tmp/security-labs-deployment-drift-issue7 bash deployment/deploy.sh
bash deployment/drift-check.sh
```

Se o alvo está correto e o repositório é que divergiu, corrigir por PR. Nunca editar
`.deployment.json` à mão.

## DRIFT_DETECTED só com `commit_mismatch`

**Sintoma.** `drift-check.sh` devolve exit 1 e o único finding é
`commit_mismatch`. Um checkout local desatualizado produz exactamente isto.

**Diagnóstico.**

```bash
bash deployment/drift-check.sh | head -40
git log --oneline -1
```

O campo `drift_class` responde directamente:

- `TRACKING_METADATA_ONLY` — o conteúdo aplicado continua a bater certo com o
  inventário; só a metadata de deployment é que ficou para trás. É drift
  esperado, não é defeito nem funcionalidade em falta.
- `CONTENT_DRIFT` — há pelo menos um ficheiro aplicado divergente. Investigar.
- `UNKNOWN` — não há prova suficiente. Nunca tratar como `IN_SYNC`.

**Ação.** Em `TRACKING_METADATA_ONLY`, alinhar o checkout (`git fetch` +
`git merge --ff-only origin/main`) e reaplicar quando for a altura própria. Não
existe correção a fazer no código por causa deste resultado.

## Milestone com contador de issues abertas errado

**Sintoma.** `gh api repos/pestoura/hermes-security-labs/milestones` mostra
`open_issues` diferente de zero num milestone cujas issues estão todas fechadas
(caso conhecido: `SVP v2 Foundation`, `open_issues=2`, issues #76, #77, #78 e
#80 todas fechadas).

**Diagnóstico.**

```bash
gh issue list --milestone "SVP v2 Foundation" --state all --json number,state
gh pr list --state all --search 'milestone:"SVP v2 Foundation"' --json number,state
```

**Ação.** Se a listagem não devolve nenhuma issue nem PR aberta, é divergência
do contador do GitHub, não trabalho por fazer. A fonte de verdade é a listagem.
Não abrir issues nem alterar o roadmap com base no contador.

## Muitas branches remotas por apagar

**Sintoma.** `git branch -r --no-merged origin/main` devolve uma contagem
elevada.

**Diagnóstico.**

```bash
git fetch --prune origin
python3 deployment/branch_inventory.py report --output /tmp/branch-inventory.json
```

**Ação.** `--no-merged` é enganador com squash merges. Usar a classificação do
inventário (`MERGED_REACHABLE`, `NO_UNIQUE_COMMITS`, `UNIQUE_COMMITS`,
`UNKNOWN`) e tratar apenas as duas primeiras como candidatas. A eliminação é
manual e autorizada à parte; ver
[Repository branch hygiene](repository-branch-hygiene.md).

## Tool unavailable

**Sintoma.** A descoberta MCP devolve menos de 12 ferramentas, ou uma ferramenta
esperada não aparece.

**Diagnóstico.**

```bash
docker inspect hermes-kali-mcp --format '{{.State.Status}} {{.State.Health.Status}}'
hermes -p pentest-lab mcp test kali-lab
```

**Ação.** Confirmar que o transporte é STDIO (`docker exec -i hermes-kali-mcp`) e que
o servidor aponta para `http://127.0.0.1:5000`. Confirmar que **não** existe
`tools.include` no perfil, porque isso reduz silenciosamente o conjunto de
ferramentas. Se uma ferramenta valida como `DEGRADED`, registar o bloqueador exato e
continuar o lifecycle: não é um stop global.

## Allowlist rejection

**Sintoma.** O pedido é recusado antes de qualquer execução.

**Causa habitual.** O runbook pede uma operação ou parâmetro fora do perfil
permitido, ou o alvo não resolve num laboratório registado.

**Ação.** Corrigir o runbook ou o binding. **Não** contornar a allowlist e não
adicionar `execute_command` ao caminho normal. Alargar o perfil é uma decisão
documentada, não uma correção local.

## Target unreachable

**Sintoma.** Erro de rede ao contactar o alvo.

**Diagnóstico.**

```bash
./platform/scripts/lab-status.sh <id>
docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker network inspect <rede-do-lab> --format '{{range $k,$v := .Containers}}{{$v.Name}} {{end}}'
```

**Causas típicas.** Kali não ligado à rede do laboratório; laboratório ainda em
`PROVISIONING`; porta publicada apenas em `127.0.0.1` e o pedido a sair de dentro de
outro container; nome de serviço errado.

## Stdout vazio, JSON inválido ou timeout

**Sintoma.** O runner devolve nada, devolve texto não parseável, ou excede o prazo.

**Regra fail-safe.** Nenhum destes casos pode ser normalizado como `secure` ou
`pass`. Devem produzir erro classificado (`RUNTIME_ERROR`, `EVIDENCE_ERROR`,
`TIMEOUT`) e a campanha regista falha, não sucesso.

**Ação.** Verificar se o alvo estava realmente *ready* e não apenas *healthy*.
Aumentar o timeout só depois de excluir readiness insuficiente. Se um caminho de
código permitir envelope vazio → resultado positivo, isso é um defeito e exige teste
de regressão.

## Kali ligado a rede residual

**Sintoma.** `docker inspect hermes-kali-mcp` mostra mais do que a rede base.

**Ação.**

```bash
docker network disconnect <rede-residual> hermes-kali-mcp
docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

O resultado aceitável, sem laboratório ativo, é apenas
`hermes-kali-mcp_hermes-kali-lab`. Depois remover o laboratório órfão a partir do
diretório Compose que o criou, com `down --remove-orphans`.

## Deployment drift

**Sintoma.** `DRIFT_DETECTED` (exit 1).

**Ação.** Ler `differences[]` e classificar antes de agir:

| Tipo | Leitura |
| --- | --- |
| `commit_mismatch` | o alvo tem outro commit; esperado logo após merge |
| `modified_file` | conteúdo divergente |
| `extra_file` | ficheiro novo ainda não registado no estado |
| `missing_file` | ficheiro em falta no alvo |
| `mode_change` | permissões alteradas |

Reaplicar `deploy.sh` só quando o repositório é a versão correta. `UNKNOWN` (exit 2)
nunca se resolve reaplicando às cegas: investigar estado ausente ou JSON inválido.

## Evidência incompleta

**Sintoma.** Falta correlação, falta saída normalizada, ou a evidência tem conteúdo
que não pode ser partilhado.

**Ação.** Não publicar. Sanear (remover tokens, cookies, cabeçalhos de autorização,
corpos com segredos), confirmar que o estado de deployment não contém conteúdo de
ficheiros, e regenerar a evidência em falta. Se não for regenerável, manter o item
aberto e reportar como não comprovado.

## Working tree ou clone errado

**Sintoma.** Alterações que "desaparecem", testes que passam sem razão, ou drift
inexplicável.

**Diagnóstico.**

```bash
git rev-parse --show-toplevel
git worktree list
git status --porcelain
git log --oneline -1
```

**Ação.** Trabalhar apenas no clone canónico
`/home/estourpm/hermes-labs/hermes-security-labs`. Clones antigos e worktrees
temporárias não são fonte de verdade. Um heurístico útil: se o `working_dir` de um
container Compose aponta para fora do clone canónico, o laboratório foi criado por
outro clone e tem de ser removido a partir daí.

## Health verde mas readiness degradada

**Sintoma.** `healthy` no Docker, mas a aplicação devolve 404, 5xx ou uma página de
arranque.

**Ação.** Nunca aceitar health como critério de aceitação. Validar a rota exata do
contrato do produto, com o método correto e a sessão/token de formulário quando
aplicável. Tolerar substituição transitória de container durante o arranque, mas com
timeout explícito e falha determinística no fim.

## Ver também

- [Operator guide](operator-guide.md)
- [Deployment tracking](deployment-tracking.md)
- [Security model](security-model.md)
