# Security Interoperability — contract candidate

Repository-owned contract candidate for `SVP2-J-02`.

## Implemented guarantees

- supported export profiles are OSCAL Assessment Results, OSCAL POA&M, CACAO 2.0 and Attack Flow;
- every export declares the exact target schema identifier and schema version used for validation;
- payloads are validated against an explicitly supplied target JSON Schema before an export envelope can be produced;
- every export carries explicit data markings;
- every export requires externally supplied evidence that a document signature has been verified;
- the export envelope records a deterministic payload SHA-256 for traceability;
- invalid target-schema payloads, missing markings and unverified signatures fail closed.

## Deliberate non-claims

This block does not bundle or fetch authoritative OSCAL, CACAO or Attack Flow schemas and does not perform production signing. Official schema acquisition/version governance, cryptographic signing and external transport remain `NOT_RUN` or `NOT_IMPLEMENTED`.

`NO_RUNTIME_CHANGE`.
