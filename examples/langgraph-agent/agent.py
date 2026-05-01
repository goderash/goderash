"""Tiny LangGraph ReAct agent wired with a GoderashCallback.

Run: `python agent.py "What's my balance?"`

The agent has two fake tools (`check_balance`, `transfer_money`). Every graph
transition and tool call lands as a typed event in the Goderash ledger.
"""

from __future__ import annotations

import os
import sys

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from goderash_adapter_langgraph import GoderashCallback
from goderash_sdk import GoderashClient


# ---- Fake banking tools (action tools require confirmation) ---------------


@tool
def check_balance(account: str = "checking") -> dict:
    """Return the current balance for an account. Read-only."""
    balances = {"checking": 4532.10, "savings": 12_050.00}
    return {"account": account, "balance": balances.get(account, 0), "currency": "USD"}


@tool
def transfer_money(source: str, destination: str, amount: float) -> dict:
    """Transfer funds between two accounts. Action; requires confirmation."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if amount > 5000:
        raise RuntimeError("daily cap exceeded")
    return {"status": "queued", "from": source, "to": destination, "amount": amount}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: agent.py \"<user message>\"")
        sys.exit(2)

    user_message = " ".join(sys.argv[1:])

    # 1. Initialize Goderash. Reads API key + tenant + endpoint from env.
    goderash = GoderashClient(agent_id="langgraph-example-v1")

    # 2. Create a graph. (Any LangGraph / LangChain graph works.)
    model = ChatAnthropic(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
        temperature=0,
    )
    graph = create_react_agent(model, tools=[check_balance, transfer_money])

    # 3. Mint a Goderash context for this user turn and attach the callback.
    ctx = goderash.new_context()
    callback = GoderashCallback(goderash, context=ctx)

    # 4. Invoke — everything the graph does gets audited.
    result = graph.invoke(
        {"messages": [("user", user_message)]},
        config={"callbacks": [callback]},
    )

    # 5. Print the assistant's final message + flush.
    final = result["messages"][-1].content if result.get("messages") else ""
    print("\nAssistant:", final)

    goderash.flush_sync()
    print(
        f"\n[goderash] conversation_id={ctx.conversation_id} turn_id={ctx.turn_id}"
    )


if __name__ == "__main__":
    main()
