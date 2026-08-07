# Risk and Finding Lifecycle — contract candidate

Repository-owned contract candidate for `SVP2-J-01`.

## Implemented guarantees

- risk assessments keep CVSS 4.0, EPSS, KEV, asset criticality, reachability, attack-path importance, threat relevance, compensating controls, detectability and remediation cost as separate auditable components;
- every component carries an explicit source reference;
- any composite score is derived only from caller-supplied normalized weights that remain part of the assessment record;
- finding states cover `OBSERVED`, `VALIDATED`, `TRIAGED`, `ASSIGNED`, `FIXED`, `RETEST`, `VERIFIED`, `CLOSED`, `ACCEPTED_RISK` and `REGRESSED`;
- transitions are explicit and fail closed;
- root cause, systemic finding flag, before/after evidence and remediation effectiveness are preserved;
- a regression requires comparable before/after evidence and reopens the finding explicitly.

## Deliberate non-claims

No production ticketing, CVSS/EPSS feed, remediation workflow or automatic risk acceptance is invoked by this block.

`NO_RUNTIME_CHANGE`.
