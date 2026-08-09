# Contributor guide

Como alterar o repositório sem partir contratos existentes.

## 1. Criar ou alterar um runbook

1. Escolher o pack: `security/packs/api`, `security/packs/devsecops` ou
   `security/packs/ai-mcp`.
2. Criar o YAML em `runbooks/` seguindo o contrato do pack:
   - API usa `ApiPentestRunbook`;
   - DevSecOps e IA/MCP usam `SecurityRunbook`.
3. Regras invioláveis:
   - sem shell livre nem payload embebido;
   - todos os IDs de alvo têm de resolver no catálogo da plataforma;
   - estado inicial `experimental`;
   - sem credenciais, hosts externos ou dados reais.
4. Validar:

   ```bash
   python3 security/tools/securityctl.py validate
   python3 -m pytest -q security/packs/<domain>/tests -p no:cacheprovider
   ```

   As contagens por domínio mudam quando se adiciona um runbook; atualizar qualquer
   teste que as fixe, na mesma PR.

## 2. Criar um binding

O único ponto de ligação autorizado é
[`security/bindings/labs.yaml`](../security/bindings/labs.yaml).

Cada entrada declara `id` do laboratório, campanhas aplicáveis e estado de
`calibration`. Requisitos herdados do catálogo:

- o laboratório existe em `platform/environments`;
- o alvo está registado no manifesto do laboratório;
- o Kali liga apenas à rede isolada do laboratório ativo;
- egress permanece desativado salvo permissão explícita do laboratório;
- o Kali desliga-se no fim de cada campanha;
- evidência fica fora do Git;
- runbooks `candidate` e `stable` exigem controlo positivo e negativo.

## 3. Criar ou alterar um laboratório / fixture

1. Adicionar o manifesto em `platform/environments/<categoria>/`. São suportados os
   dois layouts durante a migração:

   ```text
   platform/environments/<category>/<id>.yaml
   platform/environments/<category>/<id>/manifest.yaml
   ```

2. Declarar origem, versão, recursos, runtime, egress, lifecycle, reset e evidência.
3. Atualizar `platform/registry.yaml` e `platform/rollout.yaml` quando aplicável.
4. Publicar portas apenas em `127.0.0.1`. Sem exposição na LAN.
5. Preferir imagens do projeto em GHCR consumidas por **digest imutável**; nunca
   `latest` nem tags móveis.
6. Validar:

   ```bash
   python3 platform/scripts/labctl.py validate
   python3 platform/scripts/labctl.py plan
   docker compose -f <compose.yaml> config --quiet
   ```

7. Se o laboratório tiver script de lifecycle, adicionar um self-test determinístico
   sem Docker e sem rede, e ligá-lo ao CI.

## 4. Alterar um runner ou adapter

- Adapters vivem em `security/packs/<domain>/adapters/`.
- Um adapter traduz runbook em pedido tipado; não interpola conteúdo arbitrário e
  não decide autorização.
- Erros têm de ser classificados. Um runner que devolve envelope vazio, stdout vazio
  ou JSON inválido **nunca** pode ser normalizado como resultado seguro.
- Testes obrigatórios ao tocar num adapter/runner:

  ```bash
  python3 -m pytest -q security/packs/<domain>/tests -p no:cacheprovider
  ```

  incluindo contrato de erro do runner e regressões de avaliação.

## 5. Schema e convenções de nomenclatura

| Artefacto | Convenção |
| --- | --- |
| ID de laboratório | minúsculas com hífen (`juice-shop`, `wrongsecrets`) |
| Campanha | `<DOMÍNIO>-<TEMA>-<NNN>` (`API-BASELINE-001`) |
| Epic de roadmap | `SVP2-<pilar A-L>-<NN>` |
| Ficheiro Markdown | minúsculas com hífen |
| Schema de laboratório | `platform/schemas/` |
| Schema de runbook | `security/packs/<domain>/schemas/` |
| Schema de backlog | `schemas/backlog-epic.schema.json` |

YAML é canónico; JSON/CSV gerados são descartáveis e não devem ser comitados.

## 6. Testes obrigatórios

Antes de abrir PR:

```bash
python3 security/tools/securityctl.py validate      # 150/120/100/370 warnings=0
python3 -m pytest -q deployment/tests -p no:cacheprovider
python3 -m pytest -q roadmap/tests   -p no:cacheprovider
python3 -m pytest -q security/tests  -p no:cacheprovider
python3 -m pytest -q docs/tests      -p no:cacheprovider
python3 -m pytest -q security/packs/<domain>/tests -p no:cacheprovider
make lint     # reproduz o gate do CI; `ruff check .` nu NÃO é o gate
git ls-files '*.sh' | xargs -r -n1 bash -n
git diff --check
```

`pytest` na raiz sem argumentos não é um gate válido: há colisões de nomes entre
packs. O CI corre por diretório.

## 7. Definition of Ready / Definition of Done

**Ready**

- objetivo e âmbito escritos;
- alvo já registado ou o registo faz parte da alteração;
- impacto de segurança avaliado;
- gates aplicáveis identificados;
- sem dependência de segredo novo.

**Done**

- código e documentação na mesma PR;
- todos os gates aplicáveis verdes;
- evidência sanitizada quando houve execução;
- issues referenciadas com estado factual;
- sem resíduos de containers, redes, locks, worktrees ou branches locais;
- árvore limpa e `main` atualizado por fast-forward;
- se a alteração pertence a uma umbrella `SVP2-*`, o documento da concept epic
  correspondente em [`roadmap/epics/`](roadmap/epics/) está atualizado: secção 14
  (implementation notes) em cada PR, e secção 15 (as-built) preenchida com evidência
  antes de fechar a umbrella. Ver
  [architecture-documentation-lifecycle](architecture/architecture-documentation-lifecycle.md).

## 7.1 Concept epics vs umbrella epics

O desenho da plataforma v2 está documentado como 45 concept epics
([catálogo](roadmap/epic-catalogue-45.md)); a entrega continua a ser feita nas 21 umbrella
issues `SVP2-*` (#76–#96). Não se abrem issues para concept epics. Ao contribuir:

1. identifica a umbrella;
2. identifica as concept epics que a umbrella cobre no
   [mapping 45→21](roadmap/epic-catalogue-45.md#5-mapping-45--21);
3. atualiza esses documentos na mesma PR;
4. regista divergências entre intenção e implementação em vez de reescrever a intenção.

## 8. Branch, PR e CI

```text
issue → branch → commit → pull request → CI → revisão → merge
      → publicação GHCR quando aplicável → deployment local → evidências
```

- Nunca escrever diretamente em `main`.
- Uma branch por objetivo, nome descritivo (`docs/…`, `fix/…`, `feat/…`).
- Commits com prefixo convencional (`feat`, `fix`, `docs`, `test`, `ci`).
- CI obrigatório: `validate` (repository) e `security` (gitleaks).
- Merge por squash, com apagamento da branch remota.
- `Closes` apenas em issues integralmente concluídas; nunca em umbrella epics
  parcialmente feitas.
- Alterações que acrescentem um laboratório e runbooks associados devem atualizar,
  na mesma PR, `platform/environments/`, `security/packs/` e
  `security/bindings/labs.yaml` quando aplicável.

## 9. Evitar duplicação

Antes de criar seja o que for:

```bash
python3 security/tools/securityctl.py list --domain <domínio>
python3 platform/scripts/labctl.py list
grep -rn "<termo>" docs/ security/bindings/ platform/environments/
```

Se já existir algo próximo, estender em vez de duplicar. Documentação nova deve ser
ligada a partir de [`docs/README.md`](README.md) e não repetir conteúdo existente —
prefira uma ligação relativa.

## 10. Atualizar mappings e frameworks no futuro

Mapeamentos para PTES, NIST, OWASP, ATT&CK, ATLAS, CWE, CAPEC, CVE/NVD, KEV, EPSS,
OSCAL e CACAO são geridos pelo crosswalk em
[`docs/architecture/framework-crosswalk.md`](architecture/framework-crosswalk.md).

Regras ao atualizar:

- distinguir sempre integração **atual** de integração **planeada**;
- registar proveniência e data da fonte;
- não inferir equivalências fortes entre frameworks sem nível de confiança
  declarado;
- sincronização automatizada de fontes externas é **roadmap** (`SVP2-E-01`).

## Ver também

- [Repository tour](repository-tour.md)
- [Documentation governance](documentation-governance.md)
- [Getting started](getting-started.md)
