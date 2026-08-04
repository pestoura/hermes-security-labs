"""Calibrated laboratory adapters for the AI/MCP pack."""

from __future__ import annotations

from ai_mcp_runbooks.adapters.promptme import (
    LABORATORY_ID,
    PromptMeAdapter,
    build_adapter,
)

__all__ = ["LABORATORY_ID", "PromptMeAdapter", "build_adapter"]
