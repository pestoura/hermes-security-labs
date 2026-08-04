"""Handler catalogue and safe execution policy for the DevSecOps pack.

Policy decisions are taken before any process is started:

* only ``(provider, action)`` pairs in :data:`ALLOWED_HANDLERS` may run;
* only laboratory targets in :data:`ALLOWED_TARGETS` may be addressed;
* only scopes in :data:`ALLOWED_SCOPES` are accepted;
* commands are never built from payload text — see
  :mod:`devsecops_runbooks.execution` for the allowlisted argv builder.
"""

from __future__ import annotations

from typing import Any

from devsecops_runbooks.contracts import ExecutionRequest


class PolicyViolation(RuntimeError):
    """Raised when a request is refused before execution."""


#: Handlers declared by the pack. ``True`` marks a calibrated implementation.
ALLOWED_HANDLERS: dict[tuple[str, str], bool] = {
    ("secrets", "scan"): True,
    ("repository", "inventory"): False,
    ("repository", "inspect"): False,
    ("evidence", "verify"): False,
    ("sbom", "verify"): False,
    ("iac", "scan"): False,
    ("supplychain", "verify"): False,
    ("cicd", "inspect"): False,
    ("sca", "scan"): False,
    ("oci", "inspect"): False,
}

#: Laboratory identifiers the pack is allowed to address.
ALLOWED_TARGETS = frozenset(
    {
        "wrongsecrets",
        "cicd-goat",
        "damn-vulnerable-sca",
        "terragoat",
        "cdkgoat",
        "cfngoat",
        "bicepgoat",
    }
)

#: Execution scopes. ``laboratory`` is the only scope permitted to run tools.
ALLOWED_SCOPES = frozenset({"laboratory"})


def is_allowed_handler(provider: str, action: str) -> bool:
    return (provider, action) in ALLOWED_HANDLERS


def is_implemented_handler(provider: str, action: str) -> bool:
    return ALLOWED_HANDLERS.get((provider, action), False)


def authorise_request(request: ExecutionRequest, policy: dict[str, Any] | None = None) -> None:
    """Authorise ``request`` or raise :class:`PolicyViolation`.

    ``policy`` optionally carries a loaded ``ExecutionPolicy`` document; when
    supplied its ``allowed_targets``/``allowed_providers`` narrow the built-in
    defaults, they never widen them.
    """

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

    if policy.get("require_evidence_redaction", False) is True:
        # Redaction is unconditional in this pack; the check documents intent.
        pass
