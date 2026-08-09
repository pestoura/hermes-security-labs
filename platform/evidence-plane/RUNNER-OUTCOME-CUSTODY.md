# Runner outcome custody

This block connects terminal Runner Protocol outcomes to the **existing** Evidence Plane. It does not create a parallel evidence store and it does not execute an effect.

## Custody sequence

1. validate the original `runner.step.request` and terminal `runner.outcome`;
2. require the same logical campaign/run/step correlation while preserving the attempt that actually produced the outcome;
3. when `output` exists, recompute its canonical JSON SHA-256 and require a matching Runner `evidence_ref` of kind `execution`;
4. derive a deterministic execution ID from `adapter_id + request_fingerprint(request)`;
5. write the terminal outcome into the existing immutable execution-evidence layout;
6. finalize and verify the execution manifest;
7. project the verified manifest + digest-only summary into the existing Evidence Plane store with payload projection disabled.

## Exact retry behaviour

Runner request fingerprinting deliberately excludes `attempt_id` and emission time. Therefore an exact logical retry addresses the same execution ID. If the adapter replays the original terminal outcome, the custody layer re-emits the same immutable execution record and reattempts only the Evidence Plane projection.

This is essential when the effect succeeded but Evidence Plane projection temporarily failed: retrying custody must not imply a second target effect.

## Security interpretation

Runner status describes execution, not a security conclusion. This bridge therefore does **not** infer that `PASS` means secure or `FAIL` means vulnerable:

- `PASS`, `FAIL`, `INCONCLUSIVE` -> execution `completed`, evidence result `inconclusive`;
- `REFUSED` -> `completed` / `skipped`;
- `CANCELLED` -> `cancelled` / `skipped`;
- `ERROR`, `TIMED_OUT` -> `failed` / `error`.

Scenario/finding logic remains responsible for security classification.

## Canonical policy

`runner-outcome-policy.yaml` remains non-operational:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- execution manifest required;
- Evidence Plane projection required;
- payload projection disabled;
- outcome classification `sanitized`.

## Data handling

The execution-scoped record contains the validated terminal Runner outcome. Projection into the Evidence Plane stores the restricted manifest and digest-only summary; the terminal outcome payload is not projected by default. Existing LocalEvidenceStore controls provide authenticated encryption, integrity checks and append-only audit for projected records.

## Remaining integration work

This candidate is not yet part of the router transaction boundary. The next step is to make the authenticated dispatch composition require successful custody before returning operational success upstream. If custody fails after the adapter effect, a retry must invoke the adapter only to obtain its idempotent replay and then retry custody; the target effect must not repeat.
