# Security Knowledge Fabric — contract candidates

Repository-owned contract candidates for `SVP2-E-01` and `SVP2-E-02`.

## Implemented guarantees

- raw source records are immutable and identified by SHA-256;
- every record carries complete source name, source version, retrieval time and locator;
- derived relations require one or more explicit provenance records, rationale and confidence in `[0,1]`;
- source conflicts are persisted as `unresolved` and never silently selected;
- resolving a conflict requires an explicit precedence policy and selection of an assertion already present in the conflict;
- applicability may be expressed only through asset, SBOM, CPE or PURL selectors;
- the entity inventory covers CVE, CPE, PURL, CWE, CAPEC, ATT&CK, ATLAS, KEV, EPSS, CSAF, VEX, OSCAL, OWASP, assets and SBOMs.

## EPIC-38 semantic-chain contract

`semantic_chain.py` adds a repository-only resolver for the ordered semantic path:

`CVE -> CWE -> CAPEC -> ATT&CK`.

The resolver is deliberately conservative:

- all relations are bound to one immutable `knowledge_snapshot_id`;
- each hop has an explicit typed relation, confidence, provenance records and rationale;
- relation direction is fixed to `VULNERABILITY_TO_CWE`, `CWE_TO_CAPEC` and `CAPEC_TO_ATTACK`;
- no mapping produces a first-class `GAP` rather than an inferred link;
- multiple mappings produce `AMBIGUOUS` with all candidates and no silent winner, even when one has higher confidence;
- duplicate semantic assertions must be reconciled before resolution;
- a complete chain uses the weakest hop as its conservative chain confidence;
- confidence thresholds only produce advisory/review decisions and never authorization;
- chain outputs are non-executable, `ADVISORY_ONLY`, with `execution_authority = NONE`;
- authority-, execution- and secret-shaped input fields fail closed;
- relation-set and provenance sizes are bounded.

The contract consumes explicitly supplied, snapshot-scoped relations only. It does not fetch CVE, CWE, CAPEC or ATT&CK data and it does not integrate with a production planner.

## EPIC-39 ATT&CK version-migration contract

`attack_sync.py` models version-pinned ATT&CK supplied snapshots and produces deterministic migration/impact reports between two explicitly supplied versions.

The repository contract intentionally stops before external synchronization:

- datasets are `SUPPLIED_SNAPSHOT` only and declare `external_fetch = NOT_PERFORMED`;
- dataset identity is deterministic over provider, domain, version, publication timestamp, locator and normalized technique content;
- technique and STIX object identifiers must be unique and canonical;
- replacement targets must exist inside the same dataset and replacement cycles fail closed;
- migration requires a strictly newer version and publication timestamp in the same ATT&CK domain;
- reports enumerate added, removed, renamed, revoked/deprecated, replaced and STIX-object-id-changed techniques;
- historical mappings must reference the source dataset and are never rewritten;
- affected mappings carry `REVIEW_REQUIRED` and only a proposed replacement where supplied by the target snapshot;
- removed techniques, stable ATT&CK IDs pointing to different STIX object IDs and revoked/deprecated techniques without a replacement are blocking findings;
- even a no-impact migration is only `ELIGIBLE_FOR_REVIEW`; `automatic_adoption = false` always;
- outputs declare `historical_rewrite = false`, `external_sync = NOT_PERFORMED` and `execution_authority = NONE`;
- authority-, execution- and secret-shaped input fields fail closed.

No TAXII client, scheduled fetcher, upstream release poller or automatic version adoption is introduced by this contract.

## EPIC-40 NIST control knowledge layer

`control_knowledge.py` adds a repository-only control-knowledge contract over explicitly supplied NIST catalogue snapshots.

The contract is deliberately not a compliance engine:

- catalogues are `SUPPLIED_SNAPSHOT` only and declare `external_fetch = NOT_PERFORMED`;
- each control carries a canonical control identifier, objective and Knowledge Fabric provenance;
- mappings bind a control to an ATT&CK technique, `runbook:` reference or `evidence:` requirement with explicit confidence, rationale and provenance;
- mappings must reference a control that actually exists in the supplied catalogue;
- observations are explicit `OBSERVED`, `NOT_OBSERVED`, `NOT_RUN` or `INCONCLUSIVE` states and only `OBSERVED` may carry canonical Evidence Plane IDs;
- partial observation of a multi-mapping control is `REVIEW_REQUIRED`, never a positive coverage state;
- all mappings must be observed before a projection can report `MAPPED_EVIDENCE_PRESENT`;
- unmapped or unobserved controls never become a `PASS` state;
- control projection semantics are limited to `UNMAPPED`, `MAPPED_NO_OBSERVATION`, `MAPPED_EVIDENCE_PRESENT` and `REVIEW_REQUIRED`;
- every projection fixes `coverage_semantics = MAPPED_VALIDATION_COVERAGE_ONLY`;
- every projection fixes `compliance_verdict = NOT_EVALUATED` and `certification_claim = NONE`;
- evidence presence does not by itself establish control effectiveness;
- mappings/projections are `ADVISORY_ONLY` with `execution_authority = NONE`;
- authority-, execution-, secret- and compliance-shaped input fields fail closed;
- catalogue, mapping, observation, provenance and evidence collections are bounded.

This repository contract does not fetch NIST content, establish that a supplied catalogue is authoritative/current, perform a formal control assessment, issue a compliance/certification conclusion or integrate with a production reporting/planning service.

## Deliberate non-claims

No external framework feed is synchronized by these repository contracts. NVD, TAXII, KEV, EPSS, CWE, CAPEC, ATT&CK and NIST external sync operations remain `NOT_RUN`, and no graph database is selected or deployed (`NOT_IMPLEMENTED`). The semantic-chain resolver does not validate external mappings merely because they are supplied; external mapping acquisition/curation and production planner consumption remain outside this repository-only block. The ATT&CK migration contract does not prove that a supplied dataset is current, authoritative or fetched from MITRE; source acquisition, signature/provenance verification, adoption workflow and production migration remain future work. The NIST control layer does not claim formal compliance, certification or control effectiveness; authoritative catalogue acquisition, complete population, production reporting/planner consumption and assessment workflow remain future work.

Hermes / Control Plane remains the sole execution-authorization authority.

`NO_RUNTIME_CHANGE`.
