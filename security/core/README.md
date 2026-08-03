# Security Runbook Core

Deterministic engine and canonical contracts for machine-readable security runbooks.

## Responsibilities

- load and validate runbook packs;
- select applicable runbooks from target capabilities;
- enforce scope and execution policies;
- create typed action requests;
- normalise evidence and results;
- never accept free-form commands from an LLM.

The core is domain-neutral. Domain packs such as `devsecops-security-runbooks`
and `ai-mcp-security-runbooks` provide catalogs, campaigns and adapter profiles.

## Status

`v0.1.0-alpha`: static contracts and deterministic dry-run execution. No target
execution is enabled by default.
