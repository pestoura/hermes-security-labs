# Threat-Informed Validation — contract candidate

Repository-owned contract candidate for `SVP2-F-01`.

## Implemented guarantees

- every threat profile is tied to a named critical business function and a frozen knowledge snapshot;
- adversary-emulation plans are proposal artefacts and do not authorize execution;
- each emulation step declares objective, technique and intrusiveness level;
- attack-graph nodes distinguish assets, identities, trust relationships, credentials, vulnerabilities, controls and evidence;
- attack-graph edges distinguish `hypothetical` from `evidenced` paths;
- an evidenced edge requires explicit evidence identifiers;
- graph path and centrality calculations operate only on repository-owned graph data and never execute a security action.

## Deliberate non-claims

No adversary emulation, Attack Flow transport, runtime execution, credential use, lateral movement or production graph store is implemented by this block.

`NO_RUNTIME_CHANGE`.
