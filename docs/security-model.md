# Security model

Modelo de segurança aplicado hoje, com o que é **roadmap** identificado como tal.

## 1. Autorização de alvos e allowlists

- Um alvo só é válido se resolver para um laboratório registado em
  `platform/environments` e estar declarado no manifesto desse laboratório.
- A ligação autorizada é feita exclusivamente por
  [`security/bindings/labs.yaml`](../security/bindings/labs.yaml).
- Produção é deny-by-default. Não existe caminho implícito para alvos externos.
- Runbooks não contêm shell livre. Operações passam por adapters tipados.
- O perfil normal não usa `execute_command` como via de trabalho; qualquer uso é
  restrito por política e auditado.

## 2. Sistema de ficheiros

- O repositório não contém segredos, resultados brutos, imagens runtime,
  credenciais, tokens nem dados pessoais.
- Caminhos graváveis em operação: `kali-mcp/data/results/`, `.runtime/`,
  `.deployment-snapshots/` e o evidence root. Todos ignorados por Git.
- O estado de deployment (`.deployment.json`) tem modo `0600`, é escrito
  atomicamente e guarda apenas inventário: caminho, sha256, tamanho e modo. Nunca
  conteúdo de ficheiro nem valor de segredo.
- Base runtime mínima e non-root com paths graváveis formalizados é **roadmap**
  (`SVP2-C-01`).

## 3. Rede e egress

| Regra | Estado |
| --- | --- |
| uma única rede por laboratório | aplicado |
| Kali ligado apenas à rede do laboratório ativo, e desligado no fim | aplicado |
| sem egress por omissão | aplicado |
| portas publicadas apenas em `127.0.0.1`, nunca na LAN | aplicado |
| perfis de egress nomeados e versionados (`isolated`, `lab-only`, `curated-egress`, `external`) | **roadmap** (`SVP2-B-03`) |

Alvos proibidos em absoluto: LAN doméstica, Home Assistant, SPMS, o próprio host
Hermes e qualquer sistema fora de um laboratório registado.

## 4. Redaction

- Evidência partilhada é sempre sanitizada: sem tokens, cookies, cabeçalhos de
  autorização, chaves privadas ou corpos de resposta com segredos.
- Harnesses de aceitação emitem apenas metadados e um marcador booleano
  PASS/FAIL; não imprimem, não fazem hash nem persistem o valor do desafio.
- Valores sensíveis obtidos em runtime permanecem em memória do processo e não
  passam por argumentos de comando, variáveis exportadas nem ficheiros.
- O heurístico de deteção de segredos pode marcar caminhos de inventário como
  suspeitos; a verificação correta é confirmar que não há corpos de ficheiro
  embebidos no estado.

## 5. Secrets

- `.env`, `*.key`, `*.pem`, `*.crt`, `*.p12`, `*.pfx`, `*.token`, `*.secret`,
  `/secrets/` e `/credentials/` estão ignorados por Git.
- `gitleaks` corre em CI em cada push e pull request.
- Credencial de registo para o Hermes é read-only (`read:packages`), fornecida por
  stdin, guardada fora de Git, Compose, manifestos, evidência e histórico de shell.
- Não existe deployment automático de GitHub para o Hermes, nem self-hosted runner,
  nem exposição do Docker socket.
- `GITHUB_TOKEN` em workflows usa permissões mínimas (`contents: read`,
  `packages: write` quando publica).

## 6. Níveis de impacto L0–L4 — roadmap

Ainda **não implementados** como política executável. Definidos como visão futura em
`SVP2-A-02` (Rules of Engagement as Code):

| Nível | Intenção |
| --- | --- |
| L0 | leitura passiva, sem interação com o alvo |
| L1 | interação não intrusiva e idempotente |
| L2 | interação ativa sem alteração de estado persistente |
| L3 | alteração de estado no laboratório, reversível |
| L4 | operações destrutivas ou de elevado impacto, só em laboratório descartável |

Até estarem implementados, o controlo efetivo é a allowlist, o binding e o
isolamento de rede. Não assumir que existe enforcement por nível.

## 7. Ações explicitamente proibidas

- executar contra alvos fora de um laboratório registado;
- ligar o Kali a mais do que uma rede em simultâneo;
- conceder egress permanente;
- criar recursos cloud reais fora de sandbox autorizada;
- comitar segredos, evidência bruta ou catálogos derivados;
- alterar visibilidade, apagar ou retaguear packages GHCR já aceites;
- fazer deploy a partir de `latest` ou de qualquer tag móvel;
- escrever diretamente em `main` ou reescrever histórico partilhado;
- remover containers, redes ou volumes não relacionados com o laboratório em causa;
- tratar `UNKNOWN`, stdout vazio ou timeout como resultado seguro;
- publicar evidência não sanitizada.

## Ver também

- [Architecture](architecture.md)
- [Operator guide](operator-guide.md)
- [Framework crosswalk](architecture/framework-crosswalk.md)
