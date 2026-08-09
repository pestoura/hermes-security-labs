# Epic catalogue — 45 concept epics for Security Validation Platform v2

> **Status: MIXED LIFECYCLE.** `EPIC-01`, `EPIC-02` and `EPIC-15` are `FINAL`; five concept
> epics are `AS_BUILT`; the remaining concept epics are `IMPLEMENTING` or `INTENT`. All 21
> delivery umbrellas are `completed`, which is a delivery status and not a lifecycle claim
> over the concept epics they cover. The authoritative per-epic state is section 7 and the
> registry
> [`roadmap/epics/security-validation-platform-v2-concepts.yaml`](../../roadmap/epics/security-validation-platform-v2-concepts.yaml).
> The delivery backlog remains the 21 umbrella epics in
> [`roadmap/epics/security-validation-platform-v2.yaml`](../../roadmap/epics/security-validation-platform-v2.yaml).

## 1. Two distinct layers

The platform is planned at two different granularities, and they must not be confused.

| Layer | Count | Artefact | Purpose |
| --- | --- | --- | --- |
| Concept epics | 45 | `EPIC-01` … `EPIC-45`, documents in [`epics/`](epics/) and registry in [`security-validation-platform-v2-concepts.yaml`](../../roadmap/epics/security-validation-platform-v2-concepts.yaml) | Capture the full design intent, one coherent capability per entry |
| Delivery umbrellas | 21 | `SVP2-<pillar>-<NN>`, GitHub issues [#76](https://github.com/pestoura/hermes-security-labs/issues/76)–[#96](https://github.com/pestoura/hermes-security-labs/issues/96) | Units of delivery, planning, milestones and closure |

Rules:

- Concept epics **never** replace umbrella issues as delivery units.
- No GitHub issue is created for a concept epic. Work is tracked on the umbrella.
- Several concept epics map to the same umbrella; every concept epic maps to exactly one.
- Closing an umbrella requires updating the as-built section of every concept epic it covers,
  per the [documentation lifecycle contract](../architecture/architecture-documentation-lifecycle.md).

## 2. Divergences between the discussion and the current YAML

Recorded explicitly, not smoothed over:

1. The delivery YAML models **12 pillars and 9 phases (0–8)**; the 45 concept epics were
   discussed as a flat conceptual list. The pillar and phase assignment in this catalogue is a
   **derived mapping**, not an original attribute of the discussion.
2. Phase `0` exists in the delivery YAML as a hygiene reference phase and has **no** concept
   epic assigned. Concept epics start at phase 1.
3. Pillar `I` (Lab Factory and Registry, umbrella `SVP2-I-01`) has **no dedicated concept epic
   number**. Lab factory concerns are distributed across `EPIC-04` (transactional lifecycle),
   the cross-cutting Lab Factory concept in section 4, and the domain runtimes `EPIC-16`–`EPIC-20`.
   This is a real gap between the 45-item list and the 21-umbrella structure.
4. Some concept epics are broader than their umbrella (for example `EPIC-15` covers documentation
   governance which `SVP2-A-03` only partially describes). The umbrella scope is **not** changed
   by this catalogue.
5. Phase values here were chosen for dependency consistency and may differ from the phase of the
   umbrella they map to when an umbrella covers several phases of work.

## 3. Catalogue index

| ID | Title | Pillar | Phase | Priority | Umbrella | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| [`EPIC-01`](epics/EPIC-01-architecture-and-canonical-contracts.md) | Architecture and canonical contracts | A | 1 | P0 | [`SVP2-A-01`](https://github.com/pestoura/hermes-security-labs/issues/76) (#76) | — |
| [`EPIC-02`](epics/EPIC-02-single-source-of-truth-for-runtime.md) | Single source of truth for runtime | A | 1 | P0 | [`SVP2-A-01`](https://github.com/pestoura/hermes-security-labs/issues/76) (#76) | `EPIC-01` |
| [`EPIC-03`](epics/EPIC-03-typed-kali-mcp.md) | Typed Kali MCP | B | 2 | P0 | [`SVP2-B-01`](https://github.com/pestoura/hermes-security-labs/issues/79) (#79) | `EPIC-01`, `EPIC-02` |
| [`EPIC-04`](epics/EPIC-04-transactional-lifecycle-and-isolation.md) | Transactional lifecycle and isolation | B | 2 | P0 | [`SVP2-B-03`](https://github.com/pestoura/hermes-security-labs/issues/81) (#81) | `EPIC-03` |
| [`EPIC-05`](epics/EPIC-05-runner-protocol-v2.md) | Runner Protocol v2 | B | 1 | P0 | [`SVP2-B-02`](https://github.com/pestoura/hermes-security-labs/issues/80) (#80) | `EPIC-01` |
| [`EPIC-06`](epics/EPIC-06-kali-image-factory.md) | Kali Image Factory | C | 3 | P1 | [`SVP2-C-01`](https://github.com/pestoura/hermes-security-labs/issues/82) (#82) | `EPIC-03` |
| [`EPIC-07`](epics/EPIC-07-capability-registry.md) | Capability Registry | C | 3 | P0 | [`SVP2-C-02`](https://github.com/pestoura/hermes-security-labs/issues/83) (#83) | `EPIC-03`, `EPIC-06` |
| [`EPIC-08`](epics/EPIC-08-network-and-egress-policy.md) | Network and egress policy | B | 2 | P0 | [`SVP2-B-03`](https://github.com/pestoura/hermes-security-labs/issues/81) (#81) | `EPIC-04` |
| [`EPIC-09`](epics/EPIC-09-exploitation-safety.md) | Exploitation safety | A | 4 | P0 | [`SVP2-A-02`](https://github.com/pestoura/hermes-security-labs/issues/77) (#77) | `EPIC-03`, `EPIC-07` |
| [`EPIC-10`](epics/EPIC-10-evidence-plane.md) | Evidence Plane | D | 2 | P0 | [`SVP2-D-01`](https://github.com/pestoura/hermes-security-labs/issues/84) (#84) | `EPIC-05` |
| [`EPIC-11`](epics/EPIC-11-technical-observability.md) | Technical observability | D | 4 | P1 | [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) (#85) | `EPIC-10` |
| [`EPIC-12`](epics/EPIC-12-redaction-and-data-classification.md) | Redaction and data classification | D | 2 | P0 | [`SVP2-D-01`](https://github.com/pestoura/hermes-security-labs/issues/84) (#84) | `EPIC-10` |
| [`EPIC-13`](epics/EPIC-13-reliability-and-chaos-testing.md) | Reliability and chaos testing | D | 4 | P1 | [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) (#85) | `EPIC-04`, `EPIC-05`, `EPIC-10` |
| [`EPIC-14`](epics/EPIC-14-real-operations-and-maintenance.md) | Real operations and maintenance | D | 4 | P1 | [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) (#85) | `EPIC-02`, `EPIC-11` |
| [`EPIC-15`](epics/EPIC-15-backlog-and-documentation-quality.md) | Backlog and documentation quality | A | 1 | P1 | [`SVP2-A-03`](https://github.com/pestoura/hermes-security-labs/issues/78) (#78) | `EPIC-01` |
| [`EPIC-16`](epics/EPIC-16-kubernetes-runtime.md) | Kubernetes Runtime | L | 8 | P2 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-04`, `EPIC-07` |
| [`EPIC-17`](epics/EPIC-17-identity-and-active-directory-runtime.md) | Identity and Active Directory Runtime | L | 8 | P2 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-04`, `EPIC-07` |
| [`EPIC-18`](epics/EPIC-18-cloud-runtime.md) | Cloud Runtime | L | 8 | P2 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-04`, `EPIC-07`, `EPIC-08` |
| [`EPIC-19`](epics/EPIC-19-mobile-runtime.md) | Mobile Runtime | L | 8 | P3 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-04`, `EPIC-07` |
| [`EPIC-20`](epics/EPIC-20-iot-ot-and-external-hardware.md) | IoT/OT and external hardware | L | 8 | P3 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-04`, `EPIC-08`, `EPIC-09` |
| [`EPIC-21`](epics/EPIC-21-framework-crosswalk-and-canonical-methodology.md) | Framework Crosswalk and canonical methodology | E | 5 | P0 | [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) (#86) | `EPIC-01` |
| [`EPIC-22`](epics/EPIC-22-threat-informed-security-validation.md) | Threat-Informed Security Validation | F | 7 | P1 | [`SVP2-F-01`](https://github.com/pestoura/hermes-security-labs/issues/88) (#88) | `EPIC-21`, `EPIC-43` |
| [`EPIC-23`](epics/EPIC-23-attack-graph-and-attack-flow.md) | Attack Graph and Attack Flow | F | 7 | P1 | [`SVP2-F-01`](https://github.com/pestoura/hermes-security-labs/issues/88) (#88) | `EPIC-22` |
| [`EPIC-24`](epics/EPIC-24-purple-team-and-detection-validation.md) | Purple Team and detection validation | F | 7 | P1 | [`SVP2-F-02`](https://github.com/pestoura/hermes-security-labs/issues/89) (#89) | `EPIC-23`, `EPIC-11` |
| [`EPIC-25`](epics/EPIC-25-continuous-security-validation.md) | Continuous Security Validation | H | 7 | P1 | [`SVP2-H-01`](https://github.com/pestoura/hermes-security-labs/issues/91) (#91) | `EPIC-10`, `EPIC-22` |
| [`EPIC-26`](epics/EPIC-26-interoperable-playbooks-and-results.md) | Interoperable playbooks and results | J | 7 | P2 | [`SVP2-J-02`](https://github.com/pestoura/hermes-security-labs/issues/94) (#94) | `EPIC-10`, `EPIC-23` |
| [`EPIC-27`](epics/EPIC-27-risk-intelligence-and-contextual-prioritization.md) | Risk Intelligence and contextual prioritization | J | 7 | P1 | [`SVP2-J-01`](https://github.com/pestoura/hermes-security-labs/issues/93) (#93) | `EPIC-23`, `EPIC-37` |
| [`EPIC-28`](epics/EPIC-28-rules-of-engagement-as-code.md) | Rules of Engagement as Code | A | 1 | P0 | [`SVP2-A-02`](https://github.com/pestoura/hermes-security-labs/issues/77) (#77) | `EPIC-01` |
| [`EPIC-29`](epics/EPIC-29-ai-and-agentic-security.md) | AI and Agentic Security | L | 8 | P2 | [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) (#96) | `EPIC-03`, `EPIC-07` |
| [`EPIC-30`](epics/EPIC-30-supply-chain-attestations.md) | Supply-chain attestations | C | 3 | P0 | [`SVP2-C-02`](https://github.com/pestoura/hermes-security-labs/issues/83) (#83) | `EPIC-06` |
| [`EPIC-31`](epics/EPIC-31-opentelemetry-end-to-end.md) | OpenTelemetry end-to-end | D | 4 | P1 | [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) (#85) | `EPIC-11` |
| [`EPIC-32`](epics/EPIC-32-resilience-validation-and-tlpt.md) | Resilience Validation and TLPT | F | 7 | P2 | [`SVP2-F-02`](https://github.com/pestoura/hermes-security-labs/issues/89) (#89) | `EPIC-22`, `EPIC-24` |
| [`EPIC-33`](epics/EPIC-33-finding-and-remediation-lifecycle.md) | Finding and remediation lifecycle | J | 7 | P1 | [`SVP2-J-01`](https://github.com/pestoura/hermes-security-labs/issues/93) (#93) | `EPIC-10`, `EPIC-27` |
| [`EPIC-34`](epics/EPIC-34-maturity-benchmarking-and-scientific-quality.md) | Maturity, benchmarking and scientific quality | D | 4 | P2 | [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) (#85) | `EPIC-13`, `EPIC-10` |
| [`EPIC-35`](epics/EPIC-35-sdk-plugins-and-runtime-certification.md) | SDK, plugins and runtime certification | K | 6 | P2 | [`SVP2-K-01`](https://github.com/pestoura/hermes-security-labs/issues/95) (#95) | `EPIC-05`, `EPIC-07` |
| [`EPIC-36`](epics/EPIC-36-security-knowledge-fabric.md) | Security Knowledge Fabric | E | 5 | P0 | [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) (#86) | `EPIC-21` |
| [`EPIC-37`](epics/EPIC-37-vulnerability-intelligence-synchronization.md) | Vulnerability Intelligence Synchronization | E | 5 | P1 | [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) (#86) | `EPIC-36` |
| [`EPIC-38`](epics/EPIC-38-cwe-capec-attack-semantic-chain.md) | CWE/CAPEC/ATT&CK Semantic Chain | E | 5 | P1 | [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) (#86) | `EPIC-36`, `EPIC-37` |
| [`EPIC-39`](epics/EPIC-39-attack-synchronization-service.md) | ATT&CK Synchronization Service | E | 5 | P1 | [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) (#86) | `EPIC-36` |
| [`EPIC-40`](epics/EPIC-40-nist-control-knowledge-layer.md) | NIST Control Knowledge Layer | E | 5 | P1 | [`SVP2-E-02`](https://github.com/pestoura/hermes-security-labs/issues/87) (#87) | `EPIC-36`, `EPIC-21` |
| [`EPIC-41`](epics/EPIC-41-vulnerability-specific-test-synthesis.md) | Vulnerability-Specific Test Synthesis | G | 7 | P1 | [`SVP2-G-01`](https://github.com/pestoura/hermes-security-labs/issues/90) (#90) | `EPIC-38`, `EPIC-42` |
| [`EPIC-42`](epics/EPIC-42-exploit-and-validation-provider-registry.md) | Exploit and Validation Provider Registry | G | 7 | P1 | [`SVP2-G-01`](https://github.com/pestoura/hermes-security-labs/issues/90) (#90) | `EPIC-07`, `EPIC-30` |
| [`EPIC-43`](epics/EPIC-43-knowledge-driven-campaign-planner.md) | Knowledge-Driven Campaign Planner | E | 6 | P1 | [`SVP2-E-02`](https://github.com/pestoura/hermes-security-labs/issues/87) (#87) | `EPIC-36`, `EPIC-28`, `EPIC-07` |
| [`EPIC-44`](epics/EPIC-44-knowledge-quality-and-conflict-resolution.md) | Knowledge Quality and Conflict Resolution | E | 5 | P1 | [`SVP2-E-02`](https://github.com/pestoura/hermes-security-labs/issues/87) (#87) | `EPIC-36`, `EPIC-37`, `EPIC-39` |
| [`EPIC-45`](epics/EPIC-45-operational-query-and-discovery.md) | Operational Query and Discovery | E | 7 | P1 | [`SVP2-E-02`](https://github.com/pestoura/hermes-security-labs/issues/87) (#87) | `EPIC-36`, `EPIC-43`, `EPIC-33` |

## 4. Cross-cutting concepts

These are **not** numbered epics. They are recurring concerns realised across several concept
epics, and they must not be turned into new epic numbers.

| Concept | Realised through |
| --- | --- |
| Runbook Factory | `EPIC-41`, `EPIC-44`, `EPIC-15` |
| Lab Factory | `EPIC-04`, `EPIC-16`–`EPIC-20`, umbrella `SVP2-I-01` |
| Runtime / Image Factory | `EPIC-06`, `EPIC-07`, `EPIC-30` |
| Detection Validation Factory | `EPIC-24`, `EPIC-32` |
| Content promotion lifecycle | `EPIC-06`, `EPIC-41`, `EPIC-42`, `EPIC-44` |
| Vulnerable / mitigated / fixed lab variants | `EPIC-04`, `EPIC-16`–`EPIC-20`, `EPIC-33` |
| Continuous learning from campaigns | `EPIC-25`, `EPIC-34`, `EPIC-44`, `EPIC-45` |

## 5. Mapping 45 → 21

| Umbrella | Issue | Umbrella title | Concept epics | IDs |
| --- | --- | --- | --- | --- |
| [`SVP2-A-01`](https://github.com/pestoura/hermes-security-labs/issues/76) | #76 | Canonical security execution architecture and trust boundaries | 2 | `EPIC-01`, `EPIC-02` |
| [`SVP2-A-02`](https://github.com/pestoura/hermes-security-labs/issues/77) | #77 | Rules of Engagement as Code and intrusiveness levels L0-L4 | 2 | `EPIC-09`, `EPIC-28` |
| [`SVP2-A-03`](https://github.com/pestoura/hermes-security-labs/issues/78) | #78 | Governance labels definition of ready done and release roadmap | 1 | `EPIC-15` |
| [`SVP2-B-01`](https://github.com/pestoura/hermes-security-labs/issues/79) | #79 | Typed Security Execution Gateway and Kali MCP Protocol v2 | 1 | `EPIC-03` |
| [`SVP2-B-02`](https://github.com/pestoura/hermes-security-labs/issues/80) | #80 | Runner Protocol v2 with correlation cancellation and normalized errors | 1 | `EPIC-05` |
| [`SVP2-B-03`](https://github.com/pestoura/hermes-security-labs/issues/81) | #81 | Transactional lab lifecycle cleanup proof and network egress profiles | 2 | `EPIC-04`, `EPIC-08` |
| [`SVP2-C-01`](https://github.com/pestoura/hermes-security-labs/issues/82) | #82 | Minimal non-root runtime base and persistent runner layout | 1 | `EPIC-06` |
| [`SVP2-C-02`](https://github.com/pestoura/hermes-security-labs/issues/83) | #83 | Capability registry profiles and signed supply chain promotion | 2 | `EPIC-07`, `EPIC-30` |
| [`SVP2-D-01`](https://github.com/pestoura/hermes-security-labs/issues/84) | #84 | Evidence Plane v2 with chain of custody retention and replay | 2 | `EPIC-10`, `EPIC-12` |
| [`SVP2-D-02`](https://github.com/pestoura/hermes-security-labs/issues/85) | #85 | End-to-end observability chaos tests and capability maturity M0-M5 | 5 | `EPIC-11`, `EPIC-13`, `EPIC-14`, `EPIC-31`, `EPIC-34` |
| [`SVP2-E-01`](https://github.com/pestoura/hermes-security-labs/issues/86) | #86 | Security knowledge graph schema provenance and framework sync | 5 | `EPIC-21`, `EPIC-36`, `EPIC-37`, `EPIC-38`, `EPIC-39` |
| [`SVP2-E-02`](https://github.com/pestoura/hermes-security-labs/issues/87) | #87 | Security Knowledge API queries and per-campaign snapshots | 4 | `EPIC-40`, `EPIC-43`, `EPIC-44`, `EPIC-45` |
| [`SVP2-F-01`](https://github.com/pestoura/hermes-security-labs/issues/88) | #88 | Threat profiles adversary emulation plans and attack graph | 2 | `EPIC-22`, `EPIC-23` |
| [`SVP2-F-02`](https://github.com/pestoura/hermes-security-labs/issues/89) | #89 | Purple team outcomes detection expectations and resilience exercises | 2 | `EPIC-24`, `EPIC-32` |
| [`SVP2-G-01`](https://github.com/pestoura/hermes-security-labs/issues/90) | #90 | Vulnerability resolution chain and trusted validation provider registry | 2 | `EPIC-41`, `EPIC-42` |
| [`SVP2-H-01`](https://github.com/pestoura/hermes-security-labs/issues/91) | #91 | Continuous content factories coverage analysis and promotion control | 1 | `EPIC-25` |
| [`SVP2-I-01`](https://github.com/pestoura/hermes-security-labs/issues/92) | #92 | Lab Schema v2 families isolation and deterministic reset | 0 | — (no concept epic mapped) |
| [`SVP2-J-01`](https://github.com/pestoura/hermes-security-labs/issues/93) | #93 | Auditable risk scoring and finding lifecycle | 2 | `EPIC-27`, `EPIC-33` |
| [`SVP2-J-02`](https://github.com/pestoura/hermes-security-labs/issues/94) | #94 | Interoperability with OSCAL CACAO and Attack Flow | 1 | `EPIC-26` |
| [`SVP2-K-01`](https://github.com/pestoura/hermes-security-labs/issues/95) | #95 | Extension SDKs conformance kit and certification | 1 | `EPIC-35` |
| [`SVP2-L-01`](https://github.com/pestoura/hermes-security-labs/issues/96) | #96 | Domain expansion to Kubernetes identity cloud mobile and IoT OT | 6 | `EPIC-16`, `EPIC-17`, `EPIC-18`, `EPIC-19`, `EPIC-20`, `EPIC-29` |

## 6. Mapping overview by pillar

See the split Mermaid diagrams in the
[intent document](../architecture/security-validation-platform-v2-intent.md#9-mapping-45--21).

## 7. Lifecycle state register

Delivery status and concept-epic lifecycle state are **different** dimensions and are
reconciled here, not smoothed over. All 21 delivery umbrellas are `completed`; only
eight concept epics have reached `AS_BUILT` or `FINAL`. A `completed` umbrella therefore
records that its declared delivery acceptance criteria were met with gated evidence, and
never implies that every concept epic it covers is `FINAL`. Promotion to `AS_BUILT` or
`FINAL` requires section 15 of the concept epic document to be populated with evidence, as
required by the
[documentation lifecycle contract](../architecture/architecture-documentation-lifecycle.md).

| Lifecycle state | Concept epics |
| --- | --- |
| `FINAL` | 3 |
| `AS_BUILT` | 5 |
| `IMPLEMENTING` | 29 |
| `INTENT` | 8 |
| **Total** | **45** |

| ID | Concept lifecycle | Umbrella | Umbrella delivery status |
| --- | --- | --- | --- |
| [`EPIC-01`](epics/EPIC-01-architecture-and-canonical-contracts.md) | `FINAL` | `SVP2-A-01` (#76) | `completed` |
| [`EPIC-02`](epics/EPIC-02-single-source-of-truth-for-runtime.md) | `FINAL` | `SVP2-A-01` (#76) | `completed` |
| [`EPIC-03`](epics/EPIC-03-typed-kali-mcp.md) | `IMPLEMENTING` | `SVP2-B-01` (#79) | `completed` |
| [`EPIC-04`](epics/EPIC-04-transactional-lifecycle-and-isolation.md) | `IMPLEMENTING` | `SVP2-B-03` (#81) | `completed` |
| [`EPIC-05`](epics/EPIC-05-runner-protocol-v2.md) | `AS_BUILT` | `SVP2-B-02` (#80) | `completed` |
| [`EPIC-06`](epics/EPIC-06-kali-image-factory.md) | `IMPLEMENTING` | `SVP2-C-01` (#82) | `completed` |
| [`EPIC-07`](epics/EPIC-07-capability-registry.md) | `IMPLEMENTING` | `SVP2-C-02` (#83) | `completed` |
| [`EPIC-08`](epics/EPIC-08-network-and-egress-policy.md) | `IMPLEMENTING` | `SVP2-B-03` (#81) | `completed` |
| [`EPIC-09`](epics/EPIC-09-exploitation-safety.md) | `AS_BUILT` | `SVP2-A-02` (#77) | `completed` |
| [`EPIC-10`](epics/EPIC-10-evidence-plane.md) | `IMPLEMENTING` | `SVP2-D-01` (#84) | `completed` |
| [`EPIC-11`](epics/EPIC-11-technical-observability.md) | `IMPLEMENTING` | `SVP2-D-02` (#85) | `completed` |
| [`EPIC-12`](epics/EPIC-12-redaction-and-data-classification.md) | `IMPLEMENTING` | `SVP2-D-01` (#84) | `completed` |
| [`EPIC-13`](epics/EPIC-13-reliability-and-chaos-testing.md) | `IMPLEMENTING` | `SVP2-D-02` (#85) | `completed` |
| [`EPIC-14`](epics/EPIC-14-real-operations-and-maintenance.md) | `INTENT` | `SVP2-D-02` (#85) | `completed` |
| [`EPIC-15`](epics/EPIC-15-backlog-and-documentation-quality.md) | `FINAL` | `SVP2-A-03` (#78) | `completed` |
| [`EPIC-16`](epics/EPIC-16-kubernetes-runtime.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-17`](epics/EPIC-17-identity-and-active-directory-runtime.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-18`](epics/EPIC-18-cloud-runtime.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-19`](epics/EPIC-19-mobile-runtime.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-20`](epics/EPIC-20-iot-ot-and-external-hardware.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-21`](epics/EPIC-21-framework-crosswalk-and-canonical-methodology.md) | `AS_BUILT` | `SVP2-E-01` (#86) | `completed` |
| [`EPIC-22`](epics/EPIC-22-threat-informed-security-validation.md) | `IMPLEMENTING` | `SVP2-F-01` (#88) | `completed` |
| [`EPIC-23`](epics/EPIC-23-attack-graph-and-attack-flow.md) | `IMPLEMENTING` | `SVP2-F-01` (#88) | `completed` |
| [`EPIC-24`](epics/EPIC-24-purple-team-and-detection-validation.md) | `IMPLEMENTING` | `SVP2-F-02` (#89) | `completed` |
| [`EPIC-25`](epics/EPIC-25-continuous-security-validation.md) | `INTENT` | `SVP2-H-01` (#91) | `completed` |
| [`EPIC-26`](epics/EPIC-26-interoperable-playbooks-and-results.md) | `IMPLEMENTING` | `SVP2-J-02` (#94) | `completed` |
| [`EPIC-27`](epics/EPIC-27-risk-intelligence-and-contextual-prioritization.md) | `AS_BUILT` | `SVP2-J-01` (#93) | `completed` |
| [`EPIC-28`](epics/EPIC-28-rules-of-engagement-as-code.md) | `IMPLEMENTING` | `SVP2-A-02` (#77) | `completed` |
| [`EPIC-29`](epics/EPIC-29-ai-and-agentic-security.md) | `INTENT` | `SVP2-L-01` (#96) | `completed` |
| [`EPIC-30`](epics/EPIC-30-supply-chain-attestations.md) | `IMPLEMENTING` | `SVP2-C-02` (#83) | `completed` |
| [`EPIC-31`](epics/EPIC-31-opentelemetry-end-to-end.md) | `IMPLEMENTING` | `SVP2-D-02` (#85) | `completed` |
| [`EPIC-32`](epics/EPIC-32-resilience-validation-and-tlpt.md) | `IMPLEMENTING` | `SVP2-F-02` (#89) | `completed` |
| [`EPIC-33`](epics/EPIC-33-finding-and-remediation-lifecycle.md) | `AS_BUILT` | `SVP2-J-01` (#93) | `completed` |
| [`EPIC-34`](epics/EPIC-34-maturity-benchmarking-and-scientific-quality.md) | `IMPLEMENTING` | `SVP2-D-02` (#85) | `completed` |
| [`EPIC-35`](epics/EPIC-35-sdk-plugins-and-runtime-certification.md) | `IMPLEMENTING` | `SVP2-K-01` (#95) | `completed` |
| [`EPIC-36`](epics/EPIC-36-security-knowledge-fabric.md) | `IMPLEMENTING` | `SVP2-E-01` (#86) | `completed` |
| [`EPIC-37`](epics/EPIC-37-vulnerability-intelligence-synchronization.md) | `IMPLEMENTING` | `SVP2-E-01` (#86) | `completed` |
| [`EPIC-38`](epics/EPIC-38-cwe-capec-attack-semantic-chain.md) | `IMPLEMENTING` | `SVP2-E-01` (#86) | `completed` |
| [`EPIC-39`](epics/EPIC-39-attack-synchronization-service.md) | `IMPLEMENTING` | `SVP2-E-01` (#86) | `completed` |
| [`EPIC-40`](epics/EPIC-40-nist-control-knowledge-layer.md) | `IMPLEMENTING` | `SVP2-E-02` (#87) | `completed` |
| [`EPIC-41`](epics/EPIC-41-vulnerability-specific-test-synthesis.md) | `IMPLEMENTING` | `SVP2-G-01` (#90) | `completed` |
| [`EPIC-42`](epics/EPIC-42-exploit-and-validation-provider-registry.md) | `IMPLEMENTING` | `SVP2-G-01` (#90) | `completed` |
| [`EPIC-43`](epics/EPIC-43-knowledge-driven-campaign-planner.md) | `IMPLEMENTING` | `SVP2-E-02` (#87) | `completed` |
| [`EPIC-44`](epics/EPIC-44-knowledge-quality-and-conflict-resolution.md) | `IMPLEMENTING` | `SVP2-E-02` (#87) | `completed` |
| [`EPIC-45`](epics/EPIC-45-operational-query-and-discovery.md) | `IMPLEMENTING` | `SVP2-E-02` (#87) | `completed` |

Reconciliation rule: this table is generated from the concept registry and the delivery
backlog. If either source changes, this section must change in the same pull request;
`roadmap/tests/test_concept_catalogue.py` enforces the agreement mechanically.

## 8. Related documents

- [Lane B cross-cutting reconciliation](lane-b-cross-cutting-reconciliation.md)
- [Platform v2 intent](../architecture/security-validation-platform-v2-intent.md)
- [Architecture documentation lifecycle](../architecture/architecture-documentation-lifecycle.md)
- [Roadmap SVP v2](security-validation-platform-v2.md)
- [Reference architecture](../architecture/security-validation-reference-architecture.md)
- [Backlog README](../../roadmap/README.md)
