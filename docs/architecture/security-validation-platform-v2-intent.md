# Security Validation Platform v2 — Intent

> **Status: INTENT.** This document describes the intended end-to-end design of the
> platform. Except where a section is explicitly marked `CURRENT/IMPLEMENTED`, nothing
> here exists yet. Delivery is tracked through the 21 umbrella epics
> ([#76](https://github.com/pestoura/hermes-security-labs/issues/76)–[#96](https://github.com/pestoura/hermes-security-labs/issues/96));
> the design space is documented as 45 concept epics in the
> [epic catalogue](../roadmap/epic-catalogue-45.md).
>
> This document contains no executable offensive instructions.

## 1. Status legend

| Marker | Meaning |
| --- | --- |
| `CURRENT/IMPLEMENTED` | Exists in the repository today and is validated by CI |
| `INTENT/PLANNED` | Designed, agreed as direction, not built |
| `FUTURE/DEPENDENT` | Depends on planned work that does not exist yet; not schedulable |

Nothing in this document asserts formal compliance or certification with any framework.
Framework relationships are expressed as **aligned** or **mapped** only.

## 2. What exists today — `CURRENT/IMPLEMENTED`

| Domain | State |
| --- | --- |
| Runbooks | 370 catalogue entries validated (`api=150`, `devsecops=120`, `ai-mcp=100`, warnings=0) |
| Execution | Kali MCP with a generic command surface |
| Laboratories | Docker environments for Web/API, DevSecOps and AI/MCP, catalogued and bound |
| Deployment | `deployment/` with deploy, verify, drift-check and rollback, tri-state verdicts |
| Supply chain | GHCR adoption per environment with provenance |
| Documentation | Canonical set under [`docs/README.md`](../README.md) with automated tests |
| Backlog | 21 umbrella epics in [`roadmap/epics/security-validation-platform-v2.yaml`](../../roadmap/epics/security-validation-platform-v2.yaml) |

Structural limitations this intent addresses: untyped execution, no capability registry,
non-normalized evidence, manual framework mapping, and no threat-informed selection of
validation content.

## 3. Vision — `INTENT/PLANNED`

Answer, repeatably and auditably: *does this control prevent, detect, or fail against this
adversary behaviour, on this asset, today?*

To do that the platform separates four responsibilities and never lets one component hold
all of them:

1. **Knowledge proposes** — the knowledge fabric derives what should be validated.
2. **Hermes authorizes** — the control plane decides what may run, against what, when.
3. **Runtimes execute** — typed, bounded, isolated execution only.
4. **Evidence attests** — verdicts derive from recorded evidence, never from claims.

## 4. Principles

1. **Knowledge proposes, Hermes authorizes, runtimes execute.**
2. **Fail-safe evaluation.** Missing evidence, error or timeout never yields `PASS`.
3. **Typed over generic.** Declared capabilities replace free command execution.
4. **Isolation by default.** Default-deny egress, one network per lab, no privileged
   containers, no host network, no Docker socket, no host mounts.
5. **Provenance everywhere.** Images, knowledge, evidence and findings carry origin,
   version and confidence.
6. **Reproducible or not accepted.** Content without demonstrated reproducibility stays
   a candidate.
7. **Never auto-merge generated content.** Generation proposes; humans promote.
8. **Separate raw from sanitized.** Raw evidence never leaves its retention class.
9. **Intent is documented before it is built, and as-built is documented before closure.**

## 5. Planes

| Plane | Responsibility | Concept epics |
| --- | --- | --- |
| Control | Authorization, planning, orchestration, refusal | `EPIC-01`, `EPIC-02`, `EPIC-09`, `EPIC-28`, `EPIC-43` |
| Knowledge | Entities, relationships, provenance, synchronization, queries | `EPIC-21`, `EPIC-36`–`EPIC-45` |
| Execution | Typed gateway, runners, labs, images, capabilities, network | `EPIC-03`–`EPIC-08`, `EPIC-16`–`EPIC-20`, `EPIC-29`, `EPIC-30`, `EPIC-35` |
| Evidence | Records, custody, classification, redaction, retention, replay | `EPIC-10`, `EPIC-12` |
| Assurance | Observability, reliability, maturity, findings, risk, reporting | `EPIC-11`, `EPIC-13`, `EPIC-14`, `EPIC-22`–`EPIC-27`, `EPIC-31`–`EPIC-34` |

### 5.1 Plane diagram

```mermaid
flowchart TB
  subgraph K[Knowledge plane]
    K1[Knowledge fabric]
    K2[Framework sync]
    K3[Campaign planner]
  end
  subgraph C[Control plane - Hermes]
    C1[Rules of Engagement]
    C2[Authorization and refusal]
    C3[Campaign orchestration]
  end
  subgraph X[Execution plane]
    X1[Typed gateway]
    X2[Runners]
    X3[Laboratories]
  end
  subgraph E[Evidence plane]
    E1[Evidence records]
    E2[Custody and retention]
  end
  subgraph A[Assurance plane]
    A1[Observability]
    A2[Findings and risk]
    A3[Reporting]
  end
  K3 -->|plan proposal| C3
  C1 --> C2
  C2 -->|typed request| X1
  X1 --> X2
  X2 --> X3
  X2 --> E1
  E1 --> E2
  E2 --> A2
  X1 --> A1
  A2 --> A3
  A3 -.feedback.-> K1
```

## 6. Trust boundaries

| Boundary | Between | Crossing rule |
| --- | --- | --- |
| TB0 | Operator and control plane | Authenticated human decision; no automation may self-authorize |
| TB1 | Control plane and execution plane | Only typed requests bound to an active authorization contract |
| TB2 | Execution plane and laboratory | One network per lab, default-deny egress, no host resources |
| TB3 | Execution plane and evidence plane | Append-only evidence writes with content hashes |
| TB4 | Evidence plane and publication | Classification and redaction enforced before any export |

```mermaid
flowchart LR
  OP[Operator] -- TB0 --> CP[Control plane]
  CP -- TB1 --> XP[Execution plane]
  XP -- TB2 --> LAB[Laboratory]
  XP -- TB3 --> EV[Evidence plane]
  EV -- TB4 --> PUB[Reports and exports]
  KN[Knowledge plane] -. proposals only .-> CP
```

## 7. Trust model and intrusiveness levels — `INTENT/PLANNED`

| Level | Meaning | Minimum requirements |
| --- | --- | --- |
| L0 | Passive, read-only observation | Active contract |
| L1 | Non-intrusive interaction | Active contract, target in scope |
| L2 | Intrusive but non-destructive | Named approver, evidence capture |
| L3 | Potentially disruptive | Named approver, rollback plan, monitoring window |
| L4 | Destructive or high impact | Dual approval, rehearsed rollback, kill switch verified |

Rules: the effective ceiling is the intersection of capability level, contract ceiling and
runtime profile. A step above the ceiling is refused deterministically with a reason code.
The kill switch is effective in every active campaign state.

## 8. End-to-end campaign — `INTENT/PLANNED`

```mermaid
sequenceDiagram
  participant OP as Operator
  participant KN as Knowledge plane
  participant CP as Control plane
  participant GW as Typed gateway
  participant RN as Runner
  participant LB as Laboratory
  participant EV as Evidence plane
  OP->>CP: sign Rules of Engagement contract
  CP->>KN: request plan for asset and threat profile
  KN-->>CP: plan proposal + snapshot reference
  OP->>CP: approve plan
  CP->>GW: typed step (capability, contract ref, correlation id)
  GW->>GW: validate capability, scope, intrusiveness
  GW->>RN: dispatch step
  RN->>LB: execute within isolated lab
  LB-->>RN: observed output
  RN->>EV: write evidence (hash, classification)
  RN-->>GW: typed outcome + evidence ref
  GW-->>CP: outcome
  CP->>EV: read evidence for evaluation
  EV-->>CP: evidence records
  CP-->>OP: verdict (PASS / FAIL / UNKNOWN) with evidence links
```

`UNKNOWN` is produced whenever evidence is missing, unreadable or insufficient.

## 9. State machines — `INTENT/PLANNED`

### 9.1 Campaign

```mermaid
stateDiagram-v2
  [*] --> Planned
  Planned --> Authorized: contract active
  Authorized --> Running
  Running --> Paused: stop condition
  Paused --> Running: resumed
  Running --> Completed
  Running --> Aborted: kill switch
  Paused --> Aborted
  Completed --> Reported
  Aborted --> Reported
  Reported --> [*]
```

### 9.2 Laboratory lifecycle

```mermaid
stateDiagram-v2
  [*] --> Declared
  Declared --> Provisioning
  Provisioning --> Ready
  Provisioning --> RollingBack: failure
  Ready --> Running
  Running --> Resetting
  Resetting --> Ready
  Running --> Destroying
  Destroying --> ResidueVerified
  RollingBack --> ResidueVerified
  ResidueVerified --> [*]
```

Every terminal transition emits a residue proof. Failure to prove zero residue is a failure,
not a warning.

## 10. Factories and continuous evolution — `INTENT/PLANNED`

Four content factories share one promotion lifecycle. They are cross-cutting concepts, not
numbered epics.

| Factory | Produces | Promotion gate |
| --- | --- | --- |
| Runbook Factory | Validation content candidates | Reproducibility evidence + human review |
| Lab Factory | Laboratory definitions and variants | Deterministic reset + zero-residue proof |
| Runtime / Image Factory | Execution images and capability layers | Provenance, SBOM, signature verification |
| Detection Validation Factory | Detection expectations and outcomes | Independent defensive telemetry |

```mermaid
flowchart LR
  CAMP[Campaign results] --> GAP[Coverage and gap analysis]
  GAP --> CAND[Candidate content]
  CAND --> REV[Human review]
  REV -->|reproducible| ACC[Accepted catalogue]
  REV -->|rejected| CAND
  ACC --> CAMP
  ACC --> RET[Retirement review]
  RET --> ACC
```

### 10.1 Laboratory variants

Each laboratory family may exist in three declared variants so that both detection and
remediation can be validated:

| Variant | Purpose |
| --- | --- |
| `vulnerable` | The weakness is present and reachable |
| `mitigated` | A compensating control is in place; the weakness remains |
| `fixed` | The weakness is removed |

A validation content item is considered reproducible only when it distinguishes the
`vulnerable` variant from the `fixed` variant deterministically.

### 10.2 Continuous learning from campaigns

Campaign outcomes feed back into coverage analysis, knowledge confidence and detection
expectations. Feedback never mutates accepted content automatically; it produces proposals.

## 11. Knowledge fabric — `INTENT/PLANNED`

```mermaid
flowchart LR
  CVE[CVE] -->|is instance of| CWE[CWE]
  CWE -->|exploited by| CAPEC[CAPEC]
  CAPEC -->|realised as| TECH[ATT&CK technique]
  TECH -->|mitigated by| CTRL[NIST control]
  TECH -->|validated by| RB[Runbook]
  RB -->|produces| EV[Evidence]
  EV -->|supports| FIND[Finding]
  FIND -->|informs| RISK[Risk score]
  TECH -->|expected detection| DET[Detection expectation]
  DET --> EV
```

Every edge carries source, ingestion version and confidence. Campaign planning consumes a
pinned snapshot so historical campaigns remain reproducible.

## 12. Threat intelligence and defensive validation — `INTENT/PLANNED`

Threat profiles select techniques; the attack graph records validated preconditions and
outcomes; detection expectations turn each execution into a purple-team datapoint recorded as
prevented, detected, alerted, missed or unknown. Absent defensive telemetry yields `UNKNOWN`,
never `missed`.

## 13. Domain expansion — `FUTURE/DEPENDENT`

Kubernetes, identity, cloud, mobile, IoT/OT and AI/agentic runtimes reuse the same lab
contract, capability registry and evidence plane. None is schedulable before the runtime
foundation and the capability registry exist.

## 14. Mapping 45 → 21

The full table lives in the [epic catalogue](../roadmap/epic-catalogue-45.md#5-mapping-45--21).
The diagrams below are split by pillar group for legibility.

### 14.1 Pillars A–B — governance and runtime foundation

```mermaid
flowchart LR
  E01[EPIC-01] --> A01[SVP2-A-01]
  E02[EPIC-02] --> A01
  E28[EPIC-28] --> A02[SVP2-A-02]
  E09[EPIC-09] --> A02
  E15[EPIC-15] --> A03[SVP2-A-03]
  E03[EPIC-03] --> B01[SVP2-B-01]
  E05[EPIC-05] --> B02[SVP2-B-02]
  E04[EPIC-04] --> B03[SVP2-B-03]
  E08[EPIC-08] --> B03
```

### 14.2 Pillars C–D — factory, evidence and assurance

```mermaid
flowchart LR
  E06[EPIC-06] --> C01[SVP2-C-01]
  E07[EPIC-07] --> C02[SVP2-C-02]
  E30[EPIC-30] --> C02
  E10[EPIC-10] --> D01[SVP2-D-01]
  E12[EPIC-12] --> D01
  E11[EPIC-11] --> D02[SVP2-D-02]
  E13[EPIC-13] --> D02
  E14[EPIC-14] --> D02
  E31[EPIC-31] --> D02
  E34[EPIC-34] --> D02
```

### 14.3 Pillar E — knowledge fabric

```mermaid
flowchart LR
  E21[EPIC-21] --> E01U[SVP2-E-01]
  E36[EPIC-36] --> E01U
  E37[EPIC-37] --> E01U
  E38[EPIC-38] --> E01U
  E39[EPIC-39] --> E01U
  E40[EPIC-40] --> E02U[SVP2-E-02]
  E43[EPIC-43] --> E02U
  E44[EPIC-44] --> E02U
  E45[EPIC-45] --> E02U
```

### 14.4 Pillars F–H — threat-informed and vulnerability-specific validation

```mermaid
flowchart LR
  E22[EPIC-22] --> F01[SVP2-F-01]
  E23[EPIC-23] --> F01
  E24[EPIC-24] --> F02[SVP2-F-02]
  E32[EPIC-32] --> F02
  E41[EPIC-41] --> G01[SVP2-G-01]
  E42[EPIC-42] --> G01
  E25[EPIC-25] --> H01[SVP2-H-01]
```

### 14.5 Pillars J–L — risk, extensibility and expansion

```mermaid
flowchart LR
  E27[EPIC-27] --> J01[SVP2-J-01]
  E33[EPIC-33] --> J01
  E26[EPIC-26] --> J02[SVP2-J-02]
  E35[EPIC-35] --> K01[SVP2-K-01]
  E16[EPIC-16] --> L01[SVP2-L-01]
  E17[EPIC-17] --> L01
  E18[EPIC-18] --> L01
  E19[EPIC-19] --> L01
  E20[EPIC-20] --> L01
  E29[EPIC-29] --> L01
  I01[SVP2-I-01]:::gap
  classDef gap stroke-dasharray: 4 4
```

`SVP2-I-01` has no dedicated concept epic; lab factory concerns are distributed. This gap is
recorded in the [catalogue divergences](../roadmap/epic-catalogue-45.md#2-divergences-between-the-discussion-and-the-current-yaml).

## 15. Roadmap phases and dependencies

```mermaid
flowchart LR
  P1[Phase 1: architecture, source of truth, Runner Protocol v2] --> P2[Phase 2: typed MCP, network policy, Evidence v2]
  P2 --> P3[Phase 3: image factory and capability registry]
  P3 --> P4[Phase 4: full lifecycle, L3/L4 safety, assurance]
  P2 --> P5[Phase 5: knowledge fabric and framework sync]
  P5 --> P6[Phase 6: content factories, planner, SDK]
  P4 --> P7[Phase 7: threat-informed, purple team, risk, interoperability]
  P6 --> P7
  P7 --> P8[Phase 8: domain expansion]
```

Phase 0 in the delivery backlog is a hygiene reference phase with no concept epic assigned.

## 16. Documentation lifecycle

Every concept epic document moves through four states. The contract is defined in
[architecture-documentation-lifecycle.md](architecture-documentation-lifecycle.md).

```mermaid
stateDiagram-v2
  [*] --> INTENT
  INTENT --> IMPLEMENTING: umbrella work starts
  IMPLEMENTING --> AS_BUILT: implementation merged
  AS_BUILT --> FINAL: umbrella closed with evidence
  IMPLEMENTING --> INTENT: work deferred
  FINAL --> IMPLEMENTING: material change reopens the epic
```

## 17. Boundaries and prohibitions

- No target outside registered laboratories.
- No offensive instruction, payload or exploit code in documentation.
- No credential, token, cookie or private key in documentation, telemetry or evidence.
- No claim of certification or formal compliance with any framework.
- No functional implementation is delivered by this document.

## 18. Related documents

- [Epic catalogue — 45 concept epics](../roadmap/epic-catalogue-45.md)
- [Architecture documentation lifecycle](architecture-documentation-lifecycle.md)
- [Roadmap SVP v2](../roadmap/security-validation-platform-v2.md)
- [Reference architecture](security-validation-reference-architecture.md)
- [Framework crosswalk](framework-crosswalk.md)
- [Security knowledge fabric](security-knowledge-fabric.md)
- [Continuous content factories](continuous-content-factories.md)
- [Backlog README](../../roadmap/README.md)
