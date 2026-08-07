# Security Knowledge Fabric — contract candidate

Repository-owned contract candidate for `SVP2-E-01`.

## Implemented guarantees

- raw source records are immutable and identified by SHA-256;
- every record carries complete source name, source version, retrieval time and locator;
- derived relations require one or more explicit provenance records, rationale and confidence in `[0,1]`;
- source conflicts are persisted as `unresolved` and never silently selected;
- resolving a conflict requires an explicit precedence policy and selection of an assertion already present in the conflict;
- applicability may be expressed only through asset, SBOM, CPE or PURL selectors;
- the entity inventory covers CVE, CPE, PURL, CWE, CAPEC, ATT&CK, ATLAS, KEV, EPSS, CSAF, VEX, OSCAL, OWASP, assets and SBOMs.

## Deliberate non-claims

No external framework feed is synchronized by this block. NVD, TAXII, KEV, EPSS and other external sync operations remain `NOT_RUN`, and no graph database is selected or deployed (`NOT_IMPLEMENTED`).

`NO_RUNTIME_CHANGE`.
