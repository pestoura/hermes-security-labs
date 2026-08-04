"""Typed execution contracts and calibrated adapters for the DevSecOps pack.

The package is intentionally dependency free (standard library only) so the
runner can be copied into the Kali MCP container and executed without any
package installation step.
"""

from __future__ import annotations

from devsecops_runbooks.contracts import (
    Decision,
    Evidence,
    ExecutionRequest,
    ExecutionResult,
    Status,
)
from devsecops_runbooks.policy import (
    ALLOWED_HANDLERS,
    PolicyViolation,
    authorise_request,
    is_allowed_handler,
)
from devsecops_runbooks.sanitizer import sanitize_mapping, sanitize_text

__all__ = [
    "ALLOWED_HANDLERS",
    "Decision",
    "Evidence",
    "ExecutionRequest",
    "ExecutionResult",
    "PolicyViolation",
    "Status",
    "authorise_request",
    "is_allowed_handler",
    "sanitize_mapping",
    "sanitize_text",
]

__version__ = "0.2.0a1"
