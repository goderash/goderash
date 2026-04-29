"""Goderash LangGraph adapter.

Usage:

    from goderash_sdk import GoderashClient
    from goderash_adapter_langgraph import GoderashCallback

    goderash = GoderashClient(...)
    graph.invoke(input, config={"callbacks": [GoderashCallback(goderash)]})
"""

from .callback import GoderashCallback

__all__ = ["GoderashCallback"]
