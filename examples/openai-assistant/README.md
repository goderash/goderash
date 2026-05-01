# Example — OpenAI Assistants run with Goderash audit

```bash
cd examples/openai-assistant
uv sync

export GODERASH_API_KEY=...
export GODERASH_TENANT=demo
export GODERASH_ENDPOINT=http://localhost:8000
export OPENAI_API_KEY=sk-...

python run.py
```

Every LLM call and every tool call inside the Assistants run lands in the
Goderash ledger. After it finishes, run `/v1/verify` to confirm chain
integrity, and `/v1/packs/soc2` to download the evidence ZIP.
