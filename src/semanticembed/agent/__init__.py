"""SemanticEmbed Agent — LLM-powered structural analysis assistant.

The Claude agent is imported on first use, so the Gemini agent
(``semanticembed.agent.gemini_agent``) works without claude-agent-sdk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["create_server", "interactive", "main", "run_agent"]

if TYPE_CHECKING:
    from .agent import create_server, interactive, main, run_agent


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import agent

        return getattr(agent, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
