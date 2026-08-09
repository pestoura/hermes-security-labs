# Getting started / tutorial

Percurso mínimo para validar o repositório localmente **sem executar campanhas
ofensivas** e sem contactar alvos externos.

Se o objetivo for operar um laboratório de ponta a ponta, o caminho curto é
[Quickstart](quickstart.md). Este documento explica o porquê de cada gate.

## 1. Pré-requisitos

| Requisito | Nota |
| --- | --- |
| Linux com Docker Engine e plugin `compose` | necessário para lifecycle e alguns self-tests |
| Python 3.11+ | `python3 --version` |
| `PyYAML`, `jsonschema`, `pytest`, `ruff` | usados pelos gates |
| `git` | fluxo de contribuição |
| `bash` | wrappers de lifecycle e deployment |
| Kali MCP em execução (`hermes-kali-mcp`) | apenas para o passo de readiness |

Opcional: `shellcheck` para análise estática de shell.

Não é necessário instalar dependências globais como root. Um ambiente virtual local
é suficiente.

## 2. Clonar e confirmar o clone certo

```bash
git clone https://github.com/pestoura/hermes-security-labs.git
cd hermes-security-labs
git rev-parse --show-toplevel
git status --porcelain
git log --oneline -1
```

A árvore deve estar limpa antes de qualquer validação. Trabalhar num clone antigo ou
numa worktree temporária é a causa mais frequente de resultados enganadores.

## 3. Comandos canónicos de validação

```bash
# catálogo de laboratórios (read-only)
python3 platform/scripts/labctl.py validate
python3 platform/scripts/labctl.py list
python3 platform/scripts/labctl.py plan

# maturidade dos laboratórios contra o baseline registado (read-only)
python3 platform/scripts/lab_audit.py audit --strict
python3 platform/scripts/lab_audit.py baseline-check

# catálogo de segurança
python3 security/tools/securityctl.py validate

# testes por diretório
python3 -m pytest -q deployment/tests -p no:cacheprovider
python3 -m pytest -q roadmap/tests   -p no:cacheprovider
python3 -m pytest -q security/tests  -p no:cacheprovider
python3 -m pytest -q docs/tests      -p no:cacheprovider
python3 -m pytest -q platform/tests  -p no:cacheprovider

# lint — reproduzir o gate do CI, não o `ruff check .` nu
make lint

# sintaxe shell (só ficheiros versionados)
git ls-files '*.sh' | xargs -r -n1 bash -n
```

> Não corra `pytest` na raiz sem argumentos. Existem colisões conhecidas de nomes de
> teste entre packs; o CI corre por diretório e é esse o contrato.

## 4. Interpretar `securityctl validate`

Saída esperada:

```text
OK	api=150 devsecops=120 ai-mcp=100 total=370 warnings=0
```

| Campo | Significado |
| --- | --- |
| `api` / `devsecops` / `ai-mcp` | número de runbooks válidos por domínio |
| `total` | soma; deve ser sempre 370 no estado atual |
| `warnings` | tem de ser `0`; qualquer aviso é um gate falhado |

Contagem diferente significa runbook adicionado, removido ou inválido. `warnings>0`
significa inconsistência de schema, alvo não resolvido ou binding em falta. Em ambos
os casos o problema está no conteúdo, não no CLI.

Comandos de leitura complementares:

```bash
python3 security/tools/securityctl.py list --domain api
python3 security/tools/securityctl.py labs
python3 security/tools/securityctl.py coverage
python3 security/tools/securityctl.py catalog --output /tmp/security-catalog.json
```

O catálogo JSON é derivado e descartável. O YAML é canónico.

## 5. Validar deployment e drift

```bash
bash deployment/verify.sh
bash deployment/drift-check.sh
```

Interpretação:

| `status` | Exit | Significado |
| --- | --- | --- |
| `IN_SYNC` | 0 | estado aplicado corresponde ao commit registado |
| `DRIFT_DETECTED` | 1 | ficheiro, modo, runner, bindings ou commit divergem |
| `UNKNOWN` | 2 | estado ausente, JSON inválido ou erro inesperado |

Para reaplicar o estado a partir do commit atual (operação idempotente, exige lock):

```bash
DEPLOY_LOCK_FILE=/tmp/security-labs-deployment-drift-issue7 bash deployment/deploy.sh
```

> Os wrappers só reconhecem a forma `--target-dir=VALOR`. A forma com espaço é
> silenciosamente ignorada e recai no destino canónico.

Detalhe em [deployment tracking](deployment-tracking.md).

## 6. Validar readiness do Kali MCP (sem executar ferramentas)

```bash
docker inspect hermes-kali-mcp --format '{{.State.Status}} {{.State.Health.Status}}'
docker inspect hermes-kali-mcp \
  --format 'nets={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

hermes -p pentest-lab mcp test kali-lab
```

Esperado:

- container `running` e `healthy`;
- ligado **apenas** à rede base `hermes-kali-mcp_hermes-kali-lab` quando não há
  laboratório ativo;
- `✓ Tools discovered: 12`.

Isto é **descoberta**, não execução. Nenhuma ferramenta é invocada.

## 7. Navegar no catálogo

Localizar um **laboratório**:

```bash
python3 platform/scripts/labctl.py list --runtime docker
./platform/scripts/lab-status.sh juice-shop
```

Localizar um **runbook**:

```bash
python3 security/tools/securityctl.py list --domain devsecops | head
```

Localizar um **binding** — a ligação canónica pack ↔ campanha ↔ laboratório:

```bash
python3 security/tools/securityctl.py labs
```

Ficheiro canónico: [`security/bindings/labs.yaml`](../security/bindings/labs.yaml).

Localizar uma **capability**: no estado atual as capacidades correspondem às 12
ferramentas expostas pelo Kali MCP e aos adapters por domínio em
`security/packs/<domain>/adapters/`. Um registry de capacidades assinado é
**roadmap** (`SVP2-C-02`).

## 8. Exemplo seguro executável

O único fluxo canónico aprovado que não toca em alvos externos nem exige Docker
para o alvo é o self-test determinístico do harness sanitizado:

```bash
python3 platform/environments/devsecops/wrongsecrets/scripts/challenge3-sanitized-test.py --self-test
```

Esperado: `WRONGSECRETS_CHALLENGE3_HARNESS_SELF_TEST_OK`.

Existe também o self-test completo de lifecycle, que exercita o modelo de health e
readiness sem iniciar o laboratório real:

```bash
bash platform/environments/devsecops/wrongsecrets/scripts/lifecycle-self-test.sh
# WRONGSECRETS_LIFECYCLE_SELF_TEST_OK
```

Provisionar um laboratório real e executar uma campanha **não** faz parte deste
tutorial e exige autorização explícita do proprietário. Ver
[Operator guide](operator-guide.md).

## 9. Cleanup e confirmação final

```bash
git status --porcelain          # tem de estar vazio
git diff --check                # sem whitespace defeituoso

docker ps -a --format '{{.Names}}\t{{.Networks}}'
docker network ls

docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

Confirmação final aceitável:

- árvore Git limpa e sem branches locais órfãs da sessão;
- sem containers ou redes de laboratório residuais;
- Kali apenas na rede base;
- `drift-check.sh` em `IN_SYNC`.

## Ver também

- [Operator guide](operator-guide.md)
- [Contributor guide](contributor-guide.md)
- [Troubleshooting](troubleshooting.md)
