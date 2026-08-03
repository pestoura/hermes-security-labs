# Security Policy

- Targets must be registered in `hermes-security-labs`.
- Execution is denied outside explicit allowlists.
- Runbooks may not contain `command`, `script`, `shell` or `argv`.
- Credentials are passed by secret reference and never written to Git.
- Destructive profiles are blocked by default.
- All external effects require evidence and post-run cleanup.
