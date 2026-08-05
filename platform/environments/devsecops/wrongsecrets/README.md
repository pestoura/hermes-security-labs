# OWASP WrongSecrets

Laboratório controlado do OWASP WrongSecrets para exercícios de gestão de segredos em ambiente Docker/no-vault.

## Release

- Source: https://github.com/OWASP/wrongsecrets
- Stable release: `1.13.5`
- Immutable source commit: `2fbf78532886135c3448c238f48ffd5b0e81f7e9`
- Effective Spring profile: `without-vault`
- Scope exclusions: AWS, Azure, GCP, Kubernetes, Vault and Google Drive.

## Artefactos

### WrongSecrets

- Registry source: `docker.io/jeroenwillemsen/wrongsecrets`
- Media type: `application/vnd.oci.image.index.v1+json`
- OCI index digest: `sha256:7f09280495e427ac39e1256d2910ec7a66c95b51ee52c962722503e5c9522c7c`
- `linux/amd64` manifest digest: `sha256:a8abfafd1f10880ad6193af5c73341c3d721be31c71f812768b9300c47edc249`

### Proxy de publicação

- Registry source: `docker.io/alpine/socat`
- Build recipe source: https://github.com/alpine-docker/multi-arch-libs/tree/master/socat
- Repository license lineage: GPL-3.0; packaged Alpine Linux and socat components retain their respective upstream licenses.
- Media type: `application/vnd.oci.image.index.v1+json`
- OCI index digest: `sha256:e7b17711daaa7d49107a7193112689e91fb1a27bddd9cb0b32641b55b8e9e3b0`
- `linux/amd64` manifest digest: `sha256:7955a82d66fd43c711946ba5c499e3ec8bf494db8ce6b32ad4df5e1b13b8f1d2`

## Topologia

- Host mapping: `127.0.0.1:8082` → `wrongsecrets-proxy:8080` → `wrongsecrets:8080`.
- MCP: `wrongsecrets:8090/mcp`, disponível apenas na rede interna e nunca publicado no host.
- `wrongsecrets-internal`: bridge com `internal: true`, ligada ao target, proxy e temporariamente ao Kali.
- `wrongsecrets-publication`: bridge ligada apenas ao proxy, sem secrets ou credenciais.
- O target não tem egress externo. A única exceção de rede é o proxy de publicação sem secrets, cujo comando está fixado ao encaminhamento para `wrongsecrets:8080`.

## Lifecycle

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/smoke.sh
./scripts/connect-kali.sh
./scripts/disconnect-kali.sh
./scripts/stop.sh
./scripts/reset.sh
./scripts/destroy.sh
```

O lifecycle usa a porta fixa `8082`, valida ownership das redes Compose, mantém attach/detach do Kali idempotente e verifica target, proxy, digests, topologia, publicação localhost e egress negativo no smoke test.

## Exercícios sanitizados

### Challenge 3

O contrato canónico da release fixada usa:

- short-name `challenge-3`;
- `GET /challenge/challenge-3` para estabelecer a sessão e obter o token CSRF;
- `POST /challenge/challenge-3` com formulário `action=submit`;
- resposta obtida de `DOCKER_ENV_PASSWORD` apenas a partir do container pertencente ao projeto.

O harness versionado executa todo o fluxo dentro de um único processo Python. O valor não é colocado em argumentos, variáveis exportadas ou ficheiros, não é impresso, não é transformado em hash e é descartado após a validação booleana.

Com o laboratório já iniciado:

```bash
python3 ./scripts/challenge3-sanitized-test.py
```

Resultado público esperado:

```text
challenge3_http_status=200
challenge3_csrf=present
Challenge 3 exercise: PASS — value processed in memory and not disclosed
```

O teste determinístico, sem Docker nem HTTP, é executado pelo lifecycle self-test e pode ser chamado diretamente:

```bash
python3 ./scripts/challenge3-sanitized-test.py --self-test
```

Não devem ser usadas rotas alternativas ou inferidas, como `/challenge/3`, `/api/challenge/3` ou endpoints de spoil, para provar este gate.

### MCP

- MCP `tools/call`: resposta processada em memória e validada através de `HERMES_WRONGSECRETS_SYNTHETIC_MARKER`, que não é uma credencial.
- A resposta bruta do MCP e o conteúdo do ambiente nunca são persistidos em evidência pública.

## Limitações

- Perfil Docker/without-vault apenas.
- Integrações cloud, Kubernetes, Vault e Google Drive excluídas.
- Proxy de publicação sem secrets; porta MCP não encaminhada.
- Um único laboratório pesado ativo de cada vez.
- O target mantém `read_only: false` por compatibilidade com o runtime upstream; `/tmp` é tmpfs e não existem bind mounts do host.
