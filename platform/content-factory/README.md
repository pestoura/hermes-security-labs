# Continuous Content Factory — contract candidate

Repository-owned contract candidate for `SVP2-H-01`.

## Implemented guarantees

- external/source changes are represented as incremental events rather than full blind rebuilds;
- candidate generation is non-executable and cannot merge itself;
- reuse of bindings, fixtures and variants is preferred before new content;
- duplicate candidates are blocked automatically;
- promotion evaluates coverage delta, positive/negative controls, reproducibility, false-positive/false-negative rates, cost and staleness;
- no candidate can advance beyond `LAB_VALIDATED` without both positive and negative controls;
- integration above proposal state requires recorded human review;
- evidence-derived learning proposals never auto-merge;
- retirement and quarantine remain explicit lifecycle states.

## Deliberate non-claims

No source sync, content generation model, lab execution, image build, detection deployment or autonomous merge is run by this block.

`NO_RUNTIME_CHANGE`.
