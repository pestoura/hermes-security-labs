"""Handler catalogue and safe execution policy for the AI/MCP pack.

Policy decisions are taken before any network interaction:

* only ``(provider, action)`` pairs in :data:`ALLOWED_HANDLERS` may run;
* only laboratory targets in :data:`ALLOWED_TARGETS` may be addressed;
* only scopes in :data:`ALLOWED_SCOPES` are accepted;
* an ``ExecutionPolicy`` document may narrow the built-in allowlists, never
  widen them; the untrusted payload can never widen them either.
"""

from __future__ import annotations

from typing import Any

from ai_mcp_runbooks.contracts import ExecutionRequest


class PolicyViolation(RuntimeError):
    """Raised when a request is refused before execution."""


#: Handlers declared by the pack. ``True`` marks a calibrated implementation.
ALLOWED_HANDLERS: dict[tuple[str, str], bool] = {
    ("agent", "conversation-test"): True,
    ("agent", "discover"): False,
    ("agent", "content-test"): False,
    ("agent", "boundary-test"): False,
    ("agent", "agency-test"): False,
    ("agent", "output-test"): False,
    ("mcp", "tool-poison-test"): False,
    ("mcp", "security-test"): False,
    ("rag", "poison-test"): False,
    ("memory", "isolation-test"): False,
}

#: Laboratory identifiers the pack is allowed to address.
ALLOWED_TARGETS = frozenset(
    {
        "promptme",
        "vulnerable-mcp-servers",
        "llmforge",
        "damn-vulnerable-llm-agent",
        "prompt-injection-lab",
        "tool-poisoning-lab",
        "rag-poisoning-lab",
    }
)

#: Execution scopes. ``laboratory`` is the only scope permitted to run probes.
ALLOWED_SCOPES = frozenset({"laboratory"})


def is_allowed_handler(provider: str, action: str) -> bool:
    return (provider, action) in ALLOWED_HANDLERS


def is_implemented_handler(provider: str, action: str) -> bool:
    return ALLOWED_HANDLERS.get((provider, action), False)


def authorise_request(request: ExecutionRequest, policy: dict[str, Any] | None = None) -> None:
    """Authorise ``request`` or raise :class:`PolicyViolation`."""

    provider, action = request.handler
    if not is_allowed_handler(provider, action):
        raise PolicyViolation(f"handler {provider}/{action} is not in the allowed catalogue")

    if request.scope not in ALLOWED_SCOPES:
        raise PolicyViolation(f"scope {request.scope!r} is not permitted")

    if request.target_ref not in ALLOWED_TARGETS:
        raise PolicyViolation(f"target {request.target_ref!r} is outside the laboratory allowlist")

    if not policy:
        return

    allowed_targets = policy.get("allowed_targets")
    if allowed_targets and request.target_ref not in set(allowed_targets):
        raise PolicyViolation(f"target {request.target_ref!r} is not allowed by the execution policy")

    allowed_providers = policy.get("allowed_providers")
    if allowed_providers and provider not in set(allowed_providers):
        raise PolicyViolation(f"provider {provider!r} is not allowed by the execution policy")

    if policy.get("production_mode", False) is True:
        raise PolicyViolation("production_mode is not supported by this pack")
