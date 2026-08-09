# Security Labs change records

This directory is the canonical JDS-002 ledger for maintenance changes discovered after an accepted repository candidate, runtime checkpoint or lab-execution baseline exists.

Create `CHG-HSL-<NNN>.yaml` when a validation observation, authorization defect, target-binding defect, evidence-custody gap, reset failure, runtime incompatibility or security review requires a product change.

Use the canonical JDS-002 classes: `HOTFIX`, `BUGFIX`, `HARDENING`, `IMPROVEMENT`, `COMPATIBILITY`, `SECURITY_FIX`, `BREAKING_CHANGE`, `DOC_ONLY`.

A change record cannot authorize a target effect. Authorization and runtime promotion remain controlled by the existing Hermes/TB1/Runner/lab gates.

Historical EPIC/RTA work is not retroactively rewritten into change records. JDS-002 applies from this adoption baseline forward.
