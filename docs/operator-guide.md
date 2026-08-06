# Operator guide

Operação diária no host Hermes. Assume autorização do proprietário e âmbito restrito
a laboratórios registados.

## 1. Lifecycle

| Fase | Comando | Verificação obrigatória |
| --- | --- | --- |
| inventariar | `python3 platform/scripts/labctl.py list` | o laboratório existe no catálogo |
| validar | `./platform/scripts/lab-validate.sh` | manifesto conforme ao schema |
| provision | `./platform/scripts/lab-start.sh <id>` | readiness real, não apenas `Up` |
| estado | `./platform/scripts/lab-status.sh <id>` | health e rede corretas |
| attach | ligar o Kali só à rede do laboratório ativo | `docker inspect hermes-kali-mcp` |
| run | campanha através do control plane | âmbito validado por policy |
| detach | `docker network disconnect <rede> hermes-kali-mcp` | Kali só na rede base |
| stop | `./platform/scripts/lab-stop.sh <id>` | containers parados |
| reset | `./platform/scripts/lab-reset.sh <id>` | estado limpo e determinístico |
| destroy | `./platform/scripts/lab-destroy.sh <id>` | zero containers, redes e volumes |
| verify | `bash deployment/verify.sh` | `IN_SYNC` |

Regra fixa: **um laboratório pesado de cada vez** no hardware atual, e o Kali é
desligado da rede do laboratório no fim de cada execução, mesmo em falha.

### Prova de detach e de zero resíduo

```bash
docker inspect hermes-kali-mcp \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker ps -a --format '{{.Names}}' | grep -i <lab> || echo NO_CONTAINERS
docker network ls --format '{{.Name}}' | grep -i <lab> || echo NO_NETWORKS
```

Só se aceita `CLEAN` com a saída negativa explícita. Ausência de verificação não é
prova.

## 2. Locks, idempotência e recuperação

- Operações de deployment usam um lock exclusivo. O nome canónico é
  `security-labs-deployment-drift-issue7`; contenção devolve exit `5` e nomeia o
  lock em stderr.
- `deploy.sh` é idempotente: reaplicar o mesmo commit não altera nada.
- Escrita de estado é atómica (`mkstemp` + `fsync` + `os.replace`), modo `0600`.
- Se um processo morrer com o lock retido, confirme que não há processo vivo antes
  de o remover, e só depois repita a operação.
- Cleanup é idempotente por desenho: repetir `down --remove-orphans` é seguro.

## 3. Estados de deployment

| Estado | Exit | Ação |
| --- | --- | --- |
| `IN_SYNC` | 0 | nada a fazer |
| `DRIFT_DETECTED` | 1 | comparar `differences[]`; decidir entre reaplicar `deploy.sh` ou corrigir o repositório |
| `UNKNOWN` | 2 | investigar; nunca tratar como sucesso |

`differences[]` distingue `modified_file`, `missing_file`, `extra_file`,
`mode_change`, runner desatualizado, contagem de bindings alterada e
`commit_mismatch`. Um `commit_mismatch` após um merge é esperado até o `deploy.sh`
ser reexecutado.

## 4. Evidência, paths e retenção

- Evidência bruta fica **fora do Git**: `kali-mcp/data/results/`, `evidence/raw/` e
  o evidence root configurado. Todos ignorados por `.gitignore`.
- O estado de deployment guarda apenas inventário: caminho, sha256, tamanho e modo.
  Nunca conteúdo de ficheiros nem valores de segredos.
- Manifestos sanitizados de campanha ou de fase vivem fora do repositório
  (por exemplo em `/tmp` ou numa pasta de evidência do operador).
- Partilha externa exige sanitização: sem tokens, sem cookies, sem cabeçalhos de
  autorização, sem corpos de resposta com segredos.
- Retenção é por execução e append-only. Não reescrever evidência anterior.

## 5. Health versus readiness

Não são a mesma coisa e confundi-los produz falsos verdes.

| Conceito | Pergunta | Sinal |
| --- | --- | --- |
| health | o processo está vivo? | `docker inspect` state/health |
| readiness | o serviço responde ao contrato esperado? | resposta HTTP correta na rota certa |

Um container pode estar `healthy` e ainda não servir a aplicação. A aceitação usa
sempre readiness observada, com timeout explícito, e tolera substituição transitória
de container durante o arranque.

## 6. Stop conditions e ações proibidas

Parar imediatamente e reportar quando:

- um alvo fora de um laboratório registado é resolvido;
- o Kali aparece ligado a mais do que uma rede durante execução;
- egress inesperado é observado;
- um segredo é exposto em log, evidência ou saída de ferramenta;
- o cleanup não consegue provar ausência de resíduo (`QUARANTINED`);
- o clone ou a worktree em uso não é o canónico;
- `drift-check` devolve `UNKNOWN` durante uma operação.

Proibido em qualquer circunstância:

- alvos na LAN, Home Assistant, SPMS ou o host Hermes;
- egress permanente;
- recursos cloud reais fora de sandbox autorizada;
- deployment automático de GitHub para o Hermes;
- self-hosted runner com acesso ao Docker socket;
- reescrever histórico partilhado em `main`;
- apagar containers, redes ou volumes não relacionados com o laboratório em causa.

## 7. Recuperar de cleanup degradado

1. Identificar o âmbito exato: nome do projeto Compose, containers, redes e volumes.

   ```bash
   docker ps -a --filter "label=com.docker.compose.project=<projeto>"
   docker network ls
   ```

2. Desligar primeiro o Kali de qualquer rede de laboratório:

   ```bash
   docker network disconnect <rede-do-lab> hermes-kali-mcp
   ```

3. Descer o projeto a partir do diretório Compose que o criou:

   ```bash
   docker compose -p <projeto> -f <compose.yaml> down --remove-orphans
   ```

4. Remover apenas resíduos comprovadamente órfãos, um a um, nunca em lote cego.
5. Reconfirmar zero containers e zero redes do laboratório e o Kali só na rede base.
6. Reexecutar `bash deployment/drift-check.sh` e registar o resultado.

Se um recurso não puder ser removido com prova, deixe-o marcado como
`QUARANTINED`, documente-o e escale. Não simule sucesso.

## Ver também

- [Troubleshooting](troubleshooting.md)
- [Security model](security-model.md)
- [Deployment tracking](deployment-tracking.md)
