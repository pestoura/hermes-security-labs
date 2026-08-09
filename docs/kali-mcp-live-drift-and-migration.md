# Kali MCP e WebGoat — Deriva do runtime vivo e runbook de migração (Wave 1 Lane E2)

Este documento é **repo-first** e **read-only** relativamente ao runtime. Não
efetua qualquer mutação de host, container, rede ou imagem, nem toca em `~/.hermes`
nem no GHCR. O objetivo é registar a deriva observada entre o runtime vivo em
`~/hermes-labs/kali-mcp` e as definições canónicas do repositório
`pestoura/hermes-security-labs`, e fornecer um runbook determinístico e sem
eliminação automática para reconciliar o runtime à canónica.

## 1. Âmbito e invariantes

- Sem mutações de host/container/rede.
- Sem publicação ou alteração de imagens GHCR (fora do âmbito da Lane E2).
- Sem edição de `~/.hermes`; o perfil de conectividade é apenas exemplo.
- Nuclei permanece diferido salvo se um cenário/runbook ativo o mapear.

## 2. Estado canónico do repositório (pós root-04 / root-18 / root-05)

- `kali-mcp/compose.yaml`: `read_only: true`, `cap_drop: [all]`,
  `no-new-privileges`, `cpus/memory/pids` limitados, rede `hermes-kali-lab`
  `internal: true`, e tmpfs delimitados para `/root/.wpscan`, `/root/.cache`,
  `/root/.john`, `/root/.msf4` (WPScan/John/Metasploit escrevem com sucesso).
- `kali-mcp/compose.yaml` binds `127.0.0.1:5000` dentro do container; sem
  publicação de host.
- `platform/environments/web-api/webgoat/compose.yaml`: rede isolada
  `webgoat-lab` (`internal: true`), publicação só `127.0.0.1`, `cap_drop: [all]`,
  `no-new-privileges`, limites de CPU/RAM/pids, proxy socat em loopback.
- Validação: `test_kali_writable_tool_state.py`, `test_webgoat_egress_proxy.py`
  e `test_kali_tool_health_states.py` (PRESENT/READY/DEGRADED).

## 3. Deriva observada no runtime vivo

| Componente | Canónico (repo) | Runtime vivo `~/hermes-labs/kali-mcp` | Impacto |
|---|---|---|---|
| `/root/.wpscan` tmpfs | montado (128m) | **ausente** | WPScan DEGRADED: `/root/.wpscan` não é gravável |
| `/root/.cache` tmpfs | montado (128m) | **ausente** | caches de tool falham em escrita |
| Bind do MCP | `127.0.0.1` interno | `127.0.0.1` interno | igual; sem exposição de host |
| Registro Hermes | perfil exemplo (não usado) | nenhum | sem registro/config canónico |
| WebGoat | rede isolada + loopback + caps + limites | Docker default bridge, sem `cap_drop`/`no-new-privileges`/limites, bind público | viola baseline de isolamento |

A deriva crítica é a falta do tmpfs `/root/.wpscan` no runtime vivo: com
`read_only: true` e sem o tmpfs, o WPScan não consegue escrever o seu estado e
entra em estado DEGRADED. O validador `kali-mcp/tool_health.py` reproduz
exatamente este caso (ver `test_live_drift_fixture_classifies_degraded`).

## 4. Conectividade MCP (perfil canónico)

O repositório define `kali-mcp/config/mcp-connectivity.example.yaml` com dois
transportes, nunca `0.0.0.0`:

1. **STDIO / docker-exec** (preferido): Hermes fala MCP via
   `docker exec -i hermes-kali-mcp kali-server-mcp`. Zero listeners de rede.
2. **loopback_http** (fallback): bind `127.0.0.1:5000` e publicação de host
   `127.0.0.1:5000:5000` apenas.

O exemplo NÃO é carregado pelo runtime e NÃO deve ser copiado para `~/.hermes`.

## 5. Nuclei diferido

Nenhum cenário ou runbook ativo da Wave 1 Lane E2 referencia execução de Nuclei.
O Nuclei aparece apenas como `NOT_RUN` em `platform/vulnerability-validation/`
( provider-policy, EPICs). Consequentemente, nenhuma definição canónica de
Nuclei é adicionada nesta lane. O validador confirma `nuclei` como `ABSENT`
(imagem canónica não o instala).

## 6. Runbook de migração/aceitação (determinístico, sem eliminação automática)

Todos os comandos são operados a partir de `~/hermes-labs/hermes-security-labs`.
Nenhuma eliminação é feita automaticamente; o operador decide e executa o
`down`/`rm` explicitamente.

### 6.1 Inspeção read-only (sem mudança de estado)

```bash
# Confirmar a deriva sem mutar o runtime
docker inspect -f '{{.State.Status}}' hermes-kali-mcp
docker inspect -f '{{json .Mounts}}' hermes-kali-mcp | jq '.[].Destination'
python kali-mcp/tool_health.py \
  --compose ~/hermes-labs/kali-mcp/compose.yaml \
  --dockerfile ~/hermes-labs/kali-mcp/Dockerfile
```

O relatório deve mostrar `wpscan DEGRADED` no runtime vivo (ausência de
`/root/.wpscan`).

### 6.2 Reconciliação do Kali MCP ao canónico

```bash
# 1. Parar o runtime desatualizado (decisão explícita do operador)
docker compose -f ~/hermes-labs/kali-mcp/compose.yaml down

# 2. Copiar a definição canónica (repo) para o runtime
cp kali-mcp/compose.yaml ~/hermes-labs/kali-mcp/compose.yaml

# 3. Validar sintaxe e classificar ferramentas
docker compose -f ~/hermes-labs/kali-mcp/compose.yaml config --quiet
python kali-mcp/tool_health.py \
  --compose ~/hermes-labs/kali-mcp/compose.yaml \
  --dockerfile kali-mcp/Dockerfile
# Esperado: ALL TRACKED TOOLS READY
```

### 6.3 Reconciliação do WebGoat ao canónico

```bash
docker compose -f platform/environments/web-api/webgoat/compose.yaml down
docker compose -f platform/environments/web-api/webgoat/compose.yaml up -d
```

### 6.4 Gate de aceitação (local)

```bash
python -m pytest -q \
  platform/tests/test_kali_tool_health_states.py \
  platform/tests/test_kali_mcp_connectivity_profile.py \
  platform/tests/test_kali_writable_tool_state.py \
  platform/tests/test_webgoat_egress_proxy.py
```

Todos os testes devem passar (verde). O estado de saúde do runtime deve então
reportar WPScan `READY`.

## 7. Contrato de evidência

A migração está concluída quando: (a) o `tool_health.py` reporta
`ALL TRACKED TOOLS READY` no runtime alvo; (b) os quatro testes acima passam;
(c) o WebGoat corre em rede isolada com publicação `127.0.0.1` e capacidades
largadas. Nenhuma eliminação de recurso Docker é automática.
