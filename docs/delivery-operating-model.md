# Hermes Security Labs — Delivery Operating Model

## Purpose

This document defines how Hermes Security Labs work is delivered under JDS-001 while preserving the platform's stricter authorization, isolation, reset and evidence requirements.

Permanent progression rule:

```text
GREEN | PASS | SUPPORTED | ACCEPTED
                 ↓
        CONTINUE AUTOMATICALLY
```

A gate that did not execute is not GREEN.

## Delivery objective

Optimize for the **next usable and safely isolated lab baseline**, not catalogue size or number of installed tools.

Prefer progression such as:

```text
isolated Docker baseline
      ↓
first accepted target/scenario
      ↓
repeatable evidence + reset
      ↓
additional web/API/auth environments
      ↓
semantic execution/runbooks
      ↓
Kubernetes / VM backends
      ↓
advanced enrichment/operations
```

## WIP and execution strategy

The project does not mandate agents or a fixed lane count.

Parallel work is used only when outcomes are materially independent and host/CI capacity can support them safely. Current portfolio guidance is an upper bound:

```text
active development WIP <= 5–6 lanes
```

Use fewer lanes when environments compete for host resources, shared network policy, registry structure or acceptance infrastructure.

A lane may be executed by a human, agent, automation, CI job or other mechanism.

## Integration Controller role

For concurrent delivery, one role owns integration throughput and platform safety. It may be human or automated.

Responsibilities:

- reconcile `main`, PRs, CI, roadmap, registry and runtime evidence;
- identify the next usable lab baseline and critical path;
- keep WIP and resource pressure bounded;
- classify failures;
- integrate GREEN work;
- revalidate registry, isolation and shared baseline;
- open new work only when useful capacity exists;
- keep environment/tool/scenario support states truthful.

A failed lane does not freeze unrelated work unless it exposes a shared isolation, host-safety, registry, security or `main` defect.

## Walking skeleton and vertical slices

A lab capability is valuable only when it proves an end-to-end lifecycle:

```text
define/authorize target
    → provision
    → readiness
    → execute bounded scenario/tool
    → collect evidence
    → reset/cleanup
    → verify known state
```

The first implementation for a new backend or environment class should be the smallest safe walking skeleton through this entire lifecycle before catalogue expansion.

## Authorization and isolation are non-negotiable

Reachability is never authorization.

Offensive execution is permitted only for targets explicitly classified as approved lab/test targets. Prefer registry `target_id` resolution over arbitrary caller-supplied URLs/IPs.

Delivery pressure must not justify:

- unrestricted external targeting;
- unsafe host networking;
- unnecessary privileged containers;
- production credential sharing;
- arbitrary host mounts;
- bypassing reset/cleanup requirements;
- reporting unobserved environments as READY/SUPPORTED.

## Gate staging

Use cheap deterministic gates before expensive builds or runtime acceptance:

```text
format / lint / schema
        ↓
registry/environment validation
        ↓
targeted unit tests
        ↓
secret/security invariants
        ↓
container/build validation
        ↓
network/isolation acceptance
        ↓
health + readiness
        ↓
scenario/evidence/reset acceptance
```

Do not consume lab/runtime resources to discover failures available through static validation first.

## Failure handling

### Deterministic failure

```text
FAIL → inspect → root cause → patch → targeted retest → continue
```

No blind retries.

### Environment/product failure

Examples: image/build error, health/readiness failure, tool degraded, reset failure, scenario parser defect. Isolate that environment/lane while unrelated safe work continues.

### Global blocker

Freeze promotion for issues such as:

- network isolation failure;
- unauthorized/external target ambiguity;
- host security regression;
- production credential/state exposure;
- broken global registry;
- broken `main`;
- unsafe cleanup/reset behavior;
- destructive ambiguity;
- required human/security decision.

## Definition of Delivery

An environment or scenario is delivered only when applicable lifecycle gates are proven:

```text
DEFINED
+ AUTHORIZED
+ PROVISIONABLE
+ READY
+ ISOLATED
+ EXECUTABLE
+ EVIDENCED
+ RESET/CLEANUP PROVEN
= DELIVERED
```

A tool binary existing in an image does not imply operational readiness.

Use explicit states such as:

```text
READY
DEGRADED
FAILED
UNSUPPORTED
DISABLED
BLOCKED
```

## CI and integration rules

- prefer short-lived branches and PR validation;
- avoid equivalent duplicate CI triggers where protections allow it;
- expensive image/runtime jobs depend on fast validation whenever practical;
- keep host/runtime acceptance distinct from simple container liveness;
- use merge queue or equivalent serialized validation where concurrent GREEN PRs may conflict in shared registry/network/platform state;
- revalidate `main` after material integrations.

## Resource governance

Parallelism must respect bounded CPU, memory, disk, container and scan concurrency. The development model should explicitly avoid repeating historical pressure such as uncontrolled `/tmp`, Docker cache or evidence growth.

Cleanup must be targeted and evidence-based; do not use aggressive blanket pruning as a normal delivery shortcut.

## Product-specific delivery targets

Choose from live state, but favor baselines such as:

### A — isolated lab baseline

One real environment provisions, becomes READY, is reachable only through intended paths and resets cleanly.

### B — scenario baseline

One scenario executes through semantic/bounded tooling and emits structured evidence.

### C — repeatable retest baseline

Run → evidence → reset → rerun produces a deterministic lifecycle and links original/retest evidence.

### D — backend expansion

Introduce Kubernetes/VM/cloud-isolated backends only after the generic lifecycle contracts are proven.

## Resume rule

A resumed execution session first reconciles:

```text
main + HEAD + PRs + CI + registry + environments + roadmap + runtime evidence
```

Conversation memory is advisory only.

## Permanent algorithm

```text
DISCOVER
   ↓
RECONCILE LIVE STATE
   ↓
IDENTIFY NEXT SAFE USABLE BASELINE
   ↓
SELECT MINIMUM USEFUL WORK SET
   ↓
BOUNDED PARALLEL IMPLEMENTATION
   ↓
FAST GATES
   ↓
FAIL? ── yes ──→ FIX / RETEST
   │
   no
   ↓
INTEGRATE
   ↓
SECURITY / ISOLATION / RUNTIME ACCEPTANCE
   ↓
BASELINE GREEN
   ↓
VERSION + EVIDENCE
   ↓
NEXT BASELINE
```
