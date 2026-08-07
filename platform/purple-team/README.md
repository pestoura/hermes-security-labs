# Purple Team Outcomes — contract candidate

Repository-owned contract candidate for `SVP2-F-02`.

## Implemented guarantees

- every emulation step produces exactly one explicit outcome state;
- supported states are `PREVENTED`, `DETECTED`, `OBSERVED_NOT_DETECTED`, `DETECTED_NOT_ACTIONABLE` and `NOT_OBSERVED`;
- absence of observation can never be recorded as prevention;
- prevention and detection require explicit evidence references;
- detection expectations may reference D3FEND techniques;
- time-to-detect and time-to-contain are represented as non-negative measured durations when evidence exists;
- resilience exercises declare injects, recovery criteria and lessons learned while remaining non-executable planning artefacts.

## Deliberate non-claims

No defensive telemetry source, SIEM, EDR, containment platform, emulation engine or TIBER-EU exercise is invoked by this block.

`NO_RUNTIME_CHANGE`.
