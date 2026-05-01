# Example — Anthropic Messages with Goderash audit

```bash
cd examples/claude-sdk-agent
uv sync

export GODERASH_API_KEY=...
export GODERASH_TENANT=demo
export ANTHROPIC_API_KEY=sk-ant-...

python run.py "What's the weather in NY?"
```

Every `messages.create` call (including tool_use blocks the model returns)
is logged to the Goderash ledger.
