# SVP2 Framework Crosswalk and Canonical Methodology

This directory implements the repository-owned contract for `EPIC-21 — Framework Crosswalk and canonical methodology`.

The implementation is deliberately non-executing. It defines a versioned Security Validation Platform v2 methodology, a versioned crosswalk dataset, deterministic validation and coverage reporting. It does not fetch framework content, authorize execution or claim external certification.

## Canonical files

| File | Purpose |
| --- | --- |
| `methodology.yaml` | Project-owned end-to-end validation methodology candidate |
| `methodology.schema.json` | Strict schema for the methodology record |
| `framework-crosswalk.yaml` | Versioned advisory mapping baseline |
| `framework-crosswalk.schema.json` | Strict schema for framework and mapping records |
| `crosswalk.py` | Fail-closed validators, coverage summary and deterministic snapshot digest |

## Canonical methodology

`methodology.yaml` defines seven ordered phases:

1. `scope_authorize`
2. `discover`
3. `analyze`
4. `validate`
5. `assess_impact`
6. `report`
7. `remediate_retest`

The methodology separates control-plane authorization, execution-capable phases and non-executing analysis/reporting phases. Any execution-capable phase requires `active_authorization` as an explicit input. `scope_authorize` is `CONTROL_PLANE_ONLY` and cannot execute.

The methodology does not create authorization. Hermes / Control Plane remains the sole execution-authorization authority. Crosswalk data, external framework references and methodology phase transitions cannot create, approve or expand an `authorization_ref`.

## Framework baseline

The repository baseline currently contains manually reviewed references to:

- NIST SP 800-115, final publication dated September 2008;
- OWASP Web Security Testing Guide v4.2, using the versioned v4.2 publication path.

These references are frozen project inputs. No network request or framework synchronization occurs at runtime.

The baseline intentionally records only mappings that can be explained. Missing mappings are first-class gaps; the system does not force a relation merely to increase coverage.

The initial NIST baseline covers all seven project phases, with lower confidence where the project lifecycle is more explicit than the referenced NIST phase model. The OWASP WSTG mapping is scoped to the `web_application` domain and intentionally leaves methodology phases without a strong WSTG equivalent as gaps.

## Mapping semantics

Every mapping records:

- methodology phase;
- framework and pinned framework version;
- target reference and label;
- relation (`aligned_with`, `supports`, `informed_by`, or `overlaps`);
- confidence label and numeric score;
- rationale;
- applicability domain;
- `advisory_only: true`.

Confidence bands are deterministic:

| Label | Score |
| --- | --- |
| `low` | `0.30 <= score < 0.60` |
| `medium` | `0.60 <= score < 0.85` |
| `high` | `0.85 <= score <= 1.00` |

Crosswalk mappings use alignment language only. They are not evidence that the platform has been externally certified, and they do not establish a regulatory or assurance claim.

## Coverage semantics

`coverage_summary()` reports:

- methodology and dataset versions;
- number of methodology phases;
- number of framework baselines;
- mapping count;
- mapped phase count per framework;
- explicit gaps per framework;
- confidence distribution.

Coverage is descriptive. It never produces a `PASS` verdict and it never changes campaign authorization, execution eligibility or finding severity.

`snapshot_digest()` produces a deterministic SHA-256 over the validated methodology and crosswalk dataset after stable sorting of framework and mapping records. This allows a campaign or report to reference a frozen repository baseline later without implying that consumer integration already exists.

## Fail-closed rules

The contract refuses:

- unknown methodology/schema versions;
- methodology phase reordering or missing phases;
- execution-capable phases without `active_authorization` input;
- unknown framework identifiers;
- unpinned methodology references;
- missing framework versions/source locators;
- mappings with unknown phases or relations;
- confidence labels inconsistent with numeric scores;
- mappings without applicability and rationale;
- mappings not marked advisory-only;
- hidden authority-bearing fields such as `authorization_ref` or `execution_allowed`;
- certification/compliance language inside mapping labels or rationales;
- runtime-status claims that exceed the implemented repository boundary.

## Runtime boundary

Current status is intentionally explicit:

```yaml
authoritative_external_sync: NOT_RUN
automatic_framework_updates: NOT_IMPLEMENTED
planner_consumer_integration: NOT_IMPLEMENTED
reporting_consumer_integration: NOT_IMPLEMENTED
execution_effect: NONE
```

The methodology also records:

```yaml
external_framework_sync: NOT_RUN
planner_integration: NOT_IMPLEMENTED
reporting_integration: NOT_IMPLEMENTED
execution_authority: CONTROL_PLANE_ONLY
```

No external framework API, TAXII service, HTTP endpoint, scanner, runner, target, lab or production service is invoked by this component.

`NO_RUNTIME_CHANGE`.
