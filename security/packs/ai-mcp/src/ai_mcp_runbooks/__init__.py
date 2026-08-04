"""Typed execution contracts and calibrated adapters for the AI/MCP pack.

The package is standard-library only so the runner can be copied into the
Kali MCP container and executed without any package installation step.
"""

from __future__ import annotations

from ai_mcp_runbooks.contracts import (
    Decision,
    Evidence,
    ExecutionRequest,
    ExecutionResult,
    Status,
)
from ai_mcp_runbooks.policy import (
    ALLOWED_HANDLERS,
    PolicyViolation,
    authorise_request,
    is_allowed_handler,
    is_implemented_handler,
)
from ai_mcp_runbooks.sanitizer import sanitize_mapping, sanitize_text

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
    "is_implemented_handler",
    "sanitize_mapping",
    "sanitize_text",
]

__version__ = "0.2.0a1"
