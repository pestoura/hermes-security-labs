# Security model

## Threats addressed

- LLM-generated command injection;
- target scope escape and SSRF against management networks;
- credential disclosure in logs or Git;
- unbounded scans and denial of service;
- destructive actions without approval;
- cross-laboratory network access;
- evidence containing personal or secret data;
- false confidence from unvalidated detections.

## Controls

- fixed runner path and base64 JSON payload;
- handler allowlist and subprocess argument arrays;
- policy allowlist for hostnames and CIDRs;
- laboratory network isolation and default-deny egress;
- per-runbook max requests, timeout and response bytes;
- destructive flag blocked by default;
- secret references rather than values;
- status remains `experimental` until two-sided validation;
- results distinguish inconclusive from secure.

## Known limitations in alpha

- profile-specific result parsers are not yet calibrated;
- the bridge executable for the actual Hermes MCP transport is environment-specific;
- credentials and identity switching require an external secret resolver;
- some Kali tools may not yet be installed in the current image;
- generic `execute_command` remains broader than the desired native MCP surface.
