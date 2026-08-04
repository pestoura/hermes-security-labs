# Agent instructions

## Source of truth

- `schemas/` define os contratos formais.
- `runbooks/` contém a fonte canónica dos testes.
- `policies/` prevalece sobre decisões do planner ou do modelo.
- `runner/kali_runner.py` é a única fronteira autorizada para execução no Kali.

## Mandatory rules

1. Nunca adicionar ações de shell livre, `eval`, `exec`, `shell=True` ou comandos provenientes de texto gerado por LLM.
2. Todos os targets devem ser validados contra `allowed_hosts` ou `allowed_cidrs` antes de qualquer rede.
3. Segredos são recebidos apenas por referências externas; não os colocar em YAML, testes, logs ou artefactos.
4. Um novo handler exige schema, implementação, testes positivos/negativos e documentação do risco.
5. Um runbook só muda de `experimental` para `stable` após validação num laboratório vulnerável e num controlo negativo.
6. Alterações devem passar por issue, branch, pull request e CI.
7. Não alterar `pestoura/hermes-security-labs` a partir deste repositório.

## Definition of done

- Schema válido e ID único.
- Política de produção avaliada.
- Sem comandos livres.
- Evidência e redaction definidas.
- Resultado distingue `secure`, `vulnerable`, `inconclusive`, `skipped` e `error`.
- Caso de teste e laboratório de validação identificados.
