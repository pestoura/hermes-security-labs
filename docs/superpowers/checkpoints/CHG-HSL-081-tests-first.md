# CHG-HSL-081 tests-first RED checkpoint

Date: 2026-08-16
Change: CHG-HSL-081
Issue: #420
PR: #425
Branch: `chg-hsl-081/vault-lab-l1-signer-adapter`
Exact tests-first head: `492d2281667a7b391f12d113ef45d6c316d7b408`
Base main: `a23825138c5d0b8483c12d47911ffa0bab8c57f4`

## Purpose

Record the deliberate TDD RED state before any Vault transport or signer production implementation exists.

## Exact-SHA workflow evidence

| Workflow | Run | Result |
| --- | ---: | --- |
| `validate` | `31952617243` | **FAILURE — intended TDD RED** |
| `security` | `31952617230` | PASS |
| `Release governance` | `31952617228` | PASS |
| `Private VAmPI source-repo access deny` | `31952617201` | PASS |

The failing `validate` job was `95178326460` (`Documentation, catalogs and source-of-truth contracts`). All preceding source-of-truth/documentation/YAML gates in that job passed; the failure occurred only in `python -m pytest -q platform/tests -p no:cacheprovider`.

## RED result

```text
34 failed, 2329 passed, 7 skipped in 144.55s
```

The failure set was limited to the intentionally missing CHG-HSL-081 implementation:

1. `platform/assurance/signing_service.py` did not yet expose `canonical_signing_payload()`;
2. `platform/assurance/vault_signer_adapter.py` did not yet exist;
3. `platform/assurance/vault_transport.py` did not yet exist.

No pre-existing platform test failed. No unrelated regression was used as RED evidence.

Additional successful checks on this exact head included:

- YAML parsing: `658` files;
- documentation tests: `1111 passed`;
- runtime source-of-truth validation: PASS;
- environment audit baseline: PASS.

## Production-code state at RED

No Vault production integration existed on this checkpoint:

- no Vault endpoint implementation;
- no AppRole client implementation;
- no Vault Transit signer adapter;
- no Vault service/key provisioning;
- no credentials or trust material;
- no runtime policy enablement;
- no Runner/Kali/target effect.

Authoritative operational state remained and remains:

```text
human decision      = NO_DECISION
supplier selection  = NO_SELECTION
selected_class      = null
human_decision_id   = null
trust                = ABSENT / UNBOUND
promotion_allowed    = false
runtime_status       = NOT_RUN
execution_authority  = NONE
campaign             = BLOCKED / HOLD
```

This checkpoint proves that subsequent GREEN behavior is attributable to the CHG-HSL-081 implementation rather than to pre-existing code.
