# Validation plan

1. Install the domain runner in the authorised execution environment.
2. Configure target and secret references from `hermes-security-labs`.
3. Execute harmless discovery profiles first.
4. Add profile-specific parsers and deterministic assertions.
5. Record sanitised evidence.
6. Run a vulnerable positive control.
7. Run a secure or remediated negative control.
8. Calibrate false positives and limits.
9. Promote only the validated profile from `experimental`.
