"""Convenience wrappers that turn ordinary functions into audited ones."""

from .agent import wrap_agent
from .llm import wrap_llm
from .tool import wrap_tool

__all__ = ["wrap_agent", "wrap_llm", "wrap_tool"]
