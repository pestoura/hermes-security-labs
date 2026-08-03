# API Signal Contract

## Visao
Critérios de avaliação dos runbooks API são expressos apenas com sinais
tipados, com produtor declarado, e avaliados deterministicamente pelo módulo
`evaluation` (`vulnerable`, `secure`, `inconclusive`). Não há eval livre,
shell ou heurísticas de comprimento.

## Entidades
- `SignalDefinition`: nome, tipo (`integer|boolean|string|mapping`),
  família, `producer[]`, descrição.
- `EvaluationResult`: `decision`, `reasons`, `evaluated`.
- `normalize_execution_output(handler, output)`: converte output cru do
  executor para o dicionário de sinais esperado pelo evaluator.

## Regras
1. Um critério só pode referenciar sinais cujo `producer` contenha o handler
   do runbook.
2. Sinais desconhecidos na chamada a `evaluate_signals` geram `SignalError`.
3. Tipos errados versus o catálogo geram `SignalError`.
4. Critérios sem suporte de produtor devem usar `inconclusive_when` com
   `family_signal_producer_required`.
5. `target_reachable` e `prerequisites_missing` são obrigatórios nas
   fixtures/sinais fornecidos.

## Como adicionar uma nova família
1. Adicionar entradas em `security/packs/api/signals/signal-catalog.yaml`
   com `family`, `type` e `producer`.
2. Implementar normalizador em `evaluation/_normalize_*` se existir um
   handler novo.
3. Atualizar `HANDLER_FAMILIES` em `tools/migrate_signals.py` para incluir
   o(s) novo(s) produtor(es).
4. Regerar critérios: `python tools/migrate_signals.py`.
5. Adicionar fixtures positivas/negativas/inconclusivas.
6. Adicionar testes do evaluator e regression tests.
7. Executar `securityctl validate` e garantir `warnings=0` e `errors=0`.

## Fixtures
- `security/packs/api/fixtures/*.yaml` contêm cenários por família.
- Cada cenário cobre `vulnerable`, `secure` e `inconclusive`.
