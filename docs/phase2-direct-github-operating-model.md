# Phase 2 direct GitHub operating model

## Roles

ChatGPT is the repository implementer and independent reviewer. It creates branches, code, manifests, Compose definitions, lifecycle controls, documentation, issues and pull requests; it also resolves static, schema and CI failures directly in GitHub.

Hermes is the local execution and validation worker. It checks out an exact reviewed commit, runs the prescribed local campaign, returns sanitised evidence and reports concrete runtime failures. Hermes does not redesign repository code during an acceptance run.

## Workflow

1. ChatGPT resolves the canonical upstream source and immutable revision.
2. ChatGPT implements a complete candidate environment in GitHub.
3. GitHub CI validates YAML, manifests, rollout references and shell syntax.
4. Hermes checks out the exact candidate head and runs local Docker/Kali validation.
5. Hermes reports pass/fail evidence without secrets or offensive payloads.
6. ChatGPT fixes GitHub code directly or opens a focused finding when the failure depends on the host.
7. Only a candidate with green CI and matching local evidence is merged.

## Safety boundary

- no GitHub-hosted deployment to Hermes;
- no self-hosted runner with the Hermes Docker socket;
- no real credentials in repositories, manifests, Compose files or evidence;
- immutable upstream commits and runtime digests where available;
- target egress denied at runtime;
- localhost-only publication through a secret-free proxy;
- Kali attachment is temporary and idempotent;
- one heavy laboratory at a time;
- local failures never trigger destructive automatic repair.

## Batch status

The Phase 2 batch provides safe local candidates for all environments listed in rollout phase `devsecops-ai`, except WrongSecrets, which is developed and accepted independently in issue #57 and PR #58.

Several upstream projects require unsafe or external dependencies for their full profile. Their initial Hermes implementation is marked `CURRENT-LIMITED` and exposes a deterministic source-analysis or attack-semantics profile rather than silently enabling Docker-in-Docker, privileged mode, host sockets, cloud credentials or external model APIs.
