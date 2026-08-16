# Architecture Decision Records

This directory is the canonical Architecture Decision Record (ADR) register for Security Validation Platform v2. ADRs explain **why** a structural decision exists; the reference architecture explains the resulting model; epic documents record implementation and evidence.

## Governance

### Numbering and filenames

- identifiers are immutable and sequential: `ADR-0001`, `ADR-0002`, …;
- filenames use `ADR-NNNN-short-title.md`;
- a withdrawn or rejected number is never reused;
- supersession creates a new ADR and links both records.

### States

| State | Meaning |
| --- | --- |
| `Proposed` | under review; not authoritative |
| `Accepted` | current architectural decision |
| `Superseded` | replaced by a later ADR; retained as history |
| `Rejected` | considered but not adopted |

### Alternative dispositions

Every materially plausible alternative considered by an ADR must be retained with one explicit disposition. This is separate from the ADR's own lifecycle state.

| Disposition | Meaning |
| --- | --- |
| `Selected` | currently adopted path |
| `Deferred` | valid option deliberately postponed until a dependency, phase or trigger changes |
| `Not selected for MVP` | potentially useful later, but disproportionate or premature for the current delivery phase |
| `Rejected` | conflicts with a requirement, invariant or accepted risk posture and should not be used under the stated conditions |
| `Superseded` | previously selected path replaced by a later accepted ADR |

For every material alternative, the ADR records:

1. why that disposition applies now;
2. the main advantages and limitations that remain relevant;
3. at least one concrete `Review trigger` whenever future reconsideration is plausible.

`Deferred` and `Not selected for MVP` are not synonyms for permanently rejected. They are intentionally retained so a later architectural review can revisit earlier trade-offs without reconstructing them from chat history, issue comments or PR discussions.

### Mandatory sections

Every ADR contains:

1. metadata and status;
2. context;
3. decision;
4. positive and negative consequences;
5. security implications;
6. alternatives considered, including explicit dispositions;
7. evidence and validation;
8. review triggers.

ADRs contain no secrets, executable offensive instructions or target-specific payloads.

### When a new ADR is required

Create or supersede an ADR when a change:

- changes a plane responsibility or trust boundary;
- changes authorization or refusal authority;
- introduces or changes a cross-plane contract;
- changes a fail-safe, isolation, provenance or evidence invariant;
- introduces a new architectural source of truth;
- changes an epic dependency or materially diverges from accepted intent;
- selects one of several materially different implementation paths whose trade-offs should remain reviewable later.

Editorial clarification that does not alter behaviour or authority does not require a new ADR.

## Decision index

| ADR | Decision | Status | Primary scope |
| --- | --- | --- | --- |
| [ADR-0001](ADR-0001-plane-separation-and-authorization-authority.md) | Separate proposal, authorization, execution, evidence and assurance responsibilities; Hermes is the authorization authority | Accepted | planes and authority |
| [ADR-0002](ADR-0002-canonical-trust-boundary-numbering.md) | Number TB0–TB4 by trust-domain crossing, not by component | Accepted | trust boundaries |
| [ADR-0003](ADR-0003-typed-contracts-over-generic-execution.md) | Use versioned typed contracts instead of generic execution in the normal profile | Accepted | execution contracts |
| [ADR-0004](ADR-0004-fail-safe-evaluation.md) | Missing or invalid evidence never produces a successful security verdict | Accepted | assurance |
| [ADR-0005](ADR-0005-isolation-by-default.md) | Default to isolated networks, denied egress and prohibited host-level privileges | Accepted | runtime and labs |
| [ADR-0006](ADR-0006-versioned-source-of-truth-and-provenance.md) | Use Git and immutable revisions as the versioned source of truth with explicit provenance | Accepted | provenance and drift |
| [ADR-0007](ADR-0007-evidence-classification-and-publication.md) | Separate raw, restricted, sanitized and summary evidence; control publication at TB4 | Accepted | evidence |
| [ADR-0008](ADR-0008-human-controlled-content-promotion.md) | Generated content remains a proposal until recorded human promotion | Accepted | content lifecycle |
| [ADR-0009](ADR-0009-runtime-source-of-truth-and-drift-semantics.md) | Use the Git registry as the runtime catalogue root, keep observation non-authoritative and apply fail-safe tri-state drift | Accepted | runtime source of truth |
| [ADR-0010](ADR-0010-versioned-uuid-correlation-contract.md) | Introduce a versioned UUID correlation contract for gateway/admission integrations without rewriting legacy identifiers | Accepted | execution correlation contracts |
| [ADR-0011](ADR-0011-assurance-profiles-for-first-live-lab-promotion.md) | Split assurance profiles into LAB_L1 and PROD while failing closed to PROD when profile state is absent or invalid | Accepted | assurance profiles and promotion coupling |
| [ADR-0012](ADR-0012-signer-operation-audit-attribution.md) | Use a dedicated signer-operation attribution adapter feeding the existing AuditSink/EvidenceChain | Accepted | signer audit attribution |
| [ADR-0013](ADR-0013-signer-trust-manifest-custody.md) | Use a minimal dedicated custody bridge for signer trust manifests and defer broader custody abstraction | Accepted | signer trust evidence custody |
| [ADR-0014](ADR-0014-vault-target-architecture-deferred-implementation.md) | Prefer VAULT as the future signer custody architecture while deferring operational implementation and selection | Accepted / deferred implementation | signer custody architecture |
| [ADR-0015](ADR-0015-authorization-receipt-audit-evidence.md) | Audit receipt registration, lookup and refusal decisions through a dedicated adapter feeding the canonical AuditSink/EvidenceChain | Accepted | authorization decision audit evidence |

## Structural-decision coverage

The ADR set covers the structural principles accepted in the roadmap. A single ADR may cover related principles, but no structural principle should be left without an authoritative decision record.

| Roadmap structural decision | ADR |
| --- | --- |
| Knowledge proposes, Hermes authorizes, runtimes execute, evidence attests | ADR-0001 |
| Stable trust-domain crossings TB0–TB4 | ADR-0002 |
| Typed execution instead of generic commands | ADR-0003 |
| Fail-safe evaluation | ADR-0004 |
| Isolation and least privilege by default | ADR-0005 |
| Versioned source of truth and provenance | ADR-0006 |
| Raw and sanitized evidence separation | ADR-0007 |
| Generated content never auto-merges | ADR-0008 |
| Reproducibility before acceptance | ADR-0008 and ADR-0009 |
| Explicit authorization for higher-impact work | ADR-0001 and ADR-0005 |
| Runtime desired state remains in Git | ADR-0009 |
| Missing or unparsable drift evidence maps to UNKNOWN | ADR-0009 |
| Image digest identity is owned by runtime release | ADR-0009 |
| Gateway/admission correlation is UUID in canonical v2 without rewriting v1 identifiers | ADR-0010 |
| LAB_L1 may omit only production WORM and multi-tenant gates while keeping identity/authorization/HITL controls | ADR-0011 |
| Signer audit attribution remains a dedicated domain adapter over the canonical AuditSink | ADR-0012 |
| Signer trust manifest custody uses the existing Evidence Plane without premature generic abstraction | ADR-0013 |
| VAULT is an architectural target only; provider selection/implementation remains a later evidence-bearing decision | ADR-0014 |
| Authorization registration, lookup and refusal decisions are auditable through a dedicated domain adapter over the canonical AuditSink | ADR-0015 |

## Supersession process

1. create the replacement ADR as `Proposed`;
2. identify the earlier ADR in `Supersedes`;
3. review consequences and migration impact;
4. accept the replacement through a pull request;
5. mark the earlier ADR `Superseded` and link `Superseded by`;
6. update this index, the reference architecture and affected epic documents in the same pull request.

Historical decision text is not rewritten to make it appear consistent with a later decision. Earlier alternatives and their dispositions remain visible even if a later ADR supersedes the selected path.

## Relationship to other documents

- [Reference architecture](../security-validation-reference-architecture.md) — current canonical architecture resulting from accepted decisions.
- [Canonical contract inventory](../contracts/README.md) — ownership and lifecycle of cross-plane contracts.
- [Architecture documentation lifecycle](../architecture-documentation-lifecycle.md) — how intent becomes as-built and final documentation.
- [Runtime source-of-truth policy](../runtime-source-of-truth.md) — desired-state, observation and drift contract.
- [EPIC-01](../../roadmap/epics/EPIC-01-architecture-and-canonical-contracts.md) — delivery and evidence for the initial ADR set.
- [EPIC-02](../../roadmap/epics/EPIC-02-single-source-of-truth-for-runtime.md) — runtime catalogue and drift delivery.
- [EPIC-03](../../roadmap/epics/EPIC-03-typed-kali-mcp.md) — typed gateway/admission contract and UUID correlation migration.
