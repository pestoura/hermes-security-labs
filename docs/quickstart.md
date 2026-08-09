# Quickstart — caminho canónico curto

Percurso mínimo e factual, do clone à destruição do laboratório, com o troubleshooting
imediato de cada passo. Assume Linux com Docker Engine + plugin `compose`, Python 3.11+
e autorização do proprietário do host.

Este documento é o **caminho curto**. O detalhe está em
[Getting started](getting-started.md), [Operator guide](operator-guide.md) e
[Troubleshooting](troubleshooting.md).

```text
clone/setup → validate → start lab → connect Kali → collect evidence → destroy → troubleshoot
```

## 0. Regras que não mudam

- Um laboratório pesado de cada vez.
- O Kali liga **apenas** à rede do laboratório ativo e é desligado no fim, mesmo em falha.
- Portas publicadas só em `127.0.0.1`.
- Evidência bruta vive fora do Git.
- Ausência de prova nunca é resultado positivo.

## 1. Clone e setup

```bash
git clone https://github.com/pestoura/hermes-security-labs.git
cd hermes-security-labs
git rev-parse --show-toplevel
git status --porcelain   # tem de estar vazio

python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install pytest pyyaml jsonschema ruff
```

O clone canónico no host Hermes é `/home/estourpm/hermes-labs/hermes-security-labs`.
Trabalhar num clone antigo é a causa mais frequente de resultados enganadores.

## 2. Validate (read-only, sem Docker)

```bash
python3 platform/scripts/labctl.py validate
python3 platform/scripts/lab_audit.py audit --strict
python3 security/tools/securityctl.py validate
python3 -m pytest -q docs/tests -p no:cacheprovider
```

Esperado: catálogo válido, auditoria sem regressão de maturidade e
`OK  api=150 devsecops=120 ai-mcp=100 total=370 warnings=0`.

Nunca correr `pytest` na raiz sem argumentos: há colisões de nomes entre packs e o
contrato do CI é por diretório.

## 3. Start lab

Não existe um comando único de arranque para todos os laboratórios. A interface real
depende da população do ambiente. Ver a
[matriz de comandos de lifecycle](#7-matriz-de-comandos-de-lifecycle).

Referência com VAmPI (`runtime-managed`, com `lifecycle.sh`):

```bash
LAB=platform/environments/web-api/vampi/scripts/lifecycle.sh

bash "$LAB" start     # compose up + espera health real
bash "$LAB" status    # estado, health, mapeamento de porta, ligação do Kali
bash "$LAB" smoke     # readiness HTTP + mapeamento + isolamento
```

`start` falha se a porta de host já estiver ocupada. A porta é parametrizável:

```bash
VAMPI_HOST_PORT=5100 bash "$LAB" start
```

> Colisões conhecidas: a porta por omissão do VAmPI (`5000`) é a mesma do servidor
> MCP local, e a do DVAPI (`3000`) é a mesma que o Juice Shop publica. Definir a
> variável de porta é a forma suportada de resolver, e não editar o `compose.yaml`.
> O Juice Shop publica `127.0.0.1:3000` fixo, sem variável: nesse caso é o outro
> laboratório que tem de mudar de porta.

`smoke` só aceita `PASS` com readiness HTTP observada, mapeamento exatamente em
`127.0.0.1:<porta>` e Kali **não** ligado. Health verde não é critério de aceitação.

## 4. Connect Kali

```bash
bash "$LAB" connect-kali
docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

Esperado: rede base do Kali **mais** a rede do laboratório ativo, e nada mais.
`connect-kali` recusa ligar-se a uma rede que não pertença ao projeto Compose do
laboratório.

Descoberta de ferramentas, sem executar nenhuma:

```bash
hermes -p pentest-lab mcp test kali-lab   # ✓ Tools discovered: 12
```

## 5. Collect evidence

A evidência bruta nunca entra em Git. Caminhos canónicos, todos ignorados pelo
`.gitignore`:

| Conteúdo | Caminho |
| --- | --- |
| saída de ferramentas do Kali MCP | `kali-mcp/data/results/` |
| evidência bruta do operador | `evidence/raw/` |
| artefactos temporários de validação | `.runtime/` |
| manifesto sanitizado de campanha | fora do repositório (ex.: `/tmp`) |

Recolha e arquivo (os diretórios de dados são criados em runtime, não existem em Git):

```bash
bash kali-mcp/scripts/backup-results.sh     # cópia datada, append-only
```

Antes de partilhar seja o que for: remover tokens, cookies, cabeçalhos de
autorização e corpos de resposta com segredos. Se a evidência não for sanitizável,
não se publica e o item fica aberto como não comprovado. O contrato de
classificação (`raw`, `restricted`, `sanitized`, `summary`) está em
[`platform/evidence-plane/README.md`](../platform/evidence-plane/README.md).

## 6. Destroy e prova de zero resíduo

```bash
bash "$LAB" disconnect-kali
bash "$LAB" destroy
```

Prova obrigatória, com saída negativa explícita:

```bash
docker ps -a --format '{{.Names}}' | grep -i vampi || echo NO_CONTAINERS
docker network ls --format '{{.Name}}' | grep -i vampi || echo NO_NETWORKS
docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
git status --porcelain
```

Aceitável: `NO_CONTAINERS`, `NO_NETWORKS`, Kali apenas na rede base, árvore limpa.
Se um recurso não puder ser removido com prova, marcar `QUARANTINED`, documentar e
escalar. Não simular sucesso.

## 7. Matriz de comandos de lifecycle

| População | Ambientes | Interface |
| --- | --- | --- |
| `lifecycle.sh` unificado | `vampi`, `dvapi`, `pygoat`, `nodegoat`, `graphql-vulnerable-lab`, `crapi`, `wrongsecrets` | `bash platform/environments/<cat>/<id>/scripts/lifecycle.sh {start\|status\|smoke\|connect-kali\|disconnect-kali\|stop\|reset\|destroy}` |
| scripts discretos | `dvwa`, `webgoat` | `bash platform/environments/web-api/<id>/scripts/{start,status,smoke,connect-kali,disconnect-kali,stop,reset,destroy}.sh` |
| scripts discretos, sem Kali | `juice-shop` | `bash platform/environments/web-api/juice-shop/scripts/{start,status,smoke,stop,reset,destroy}.sh` |
| Fase 2, gerado por catálogo | 13 ambientes de `platform/phase2/environments.yaml` | `bash platform/scripts/phase2-compose-lab.sh <id> {config\|start\|status\|smoke\|connect-kali\|disconnect-kali\|stop\|reset\|destroy}` |
| `catalog-only` | restantes entradas do catálogo | sem lifecycle no repositório; só metadados |

`wrongsecrets` aceita ainda `config`. Os ambientes de Fase 2 são gerados para
`.runtime/phase2/<id>/compose.yaml` a partir do catálogo; esse ficheiro é derivado e
descartável.

> Os wrappers `platform/scripts/lab-start.sh`, `lab-stop.sh`, `lab-reset.sh` e
> `lab-destroy.sh` **não** provisionam nada. São stubs e recusam-se a correr,
> apontando para a interface real. Os wrappers read-only `lab-list.sh`,
> `lab-status.sh`, `lab-validate.sh` e `lab-plan.sh` funcionam e delegam em
> `labctl.py`.

Descoberta:

```bash
./platform/scripts/lab-list.sh --runtime docker
./platform/scripts/lab-status.sh vampi
python3 platform/scripts/lab_audit.py audit --runtime-managed
```

## 8. Troubleshoot — primeiros cortes

| Sintoma | Corte imediato |
| --- | --- |
| `start` diz que a porta está em uso | definir `<LAB>_HOST_PORT`; ver colisões conhecidas no passo 3 |
| `lab-start.sh` não arranca nada | é um stub; usar a matriz do passo 7 |
| `healthy` mas 404/5xx | health ≠ readiness; validar a rota do contrato, não o processo |
| Kali em mais do que uma rede | `docker network disconnect <rede> hermes-kali-mcp` e reconfirmar |
| Alterações que "desaparecem" | `git rev-parse --show-toplevel`; clone/worktree errado |
| `drift-check` devolve `UNKNOWN` | não reaplicar às cegas; investigar estado ausente ou JSON inválido |
| Runner com stdout vazio ou JSON inválido | erro classificado, nunca `pass` |

Catálogo completo de sintomas em [Troubleshooting](troubleshooting.md).

## Ver também

- [Getting started](getting-started.md)
- [Operator guide](operator-guide.md)
- [Troubleshooting](troubleshooting.md)
- [Contributor guide](contributor-guide.md)
- [Lab catalog maturity](lab-catalog-maturity.md)
