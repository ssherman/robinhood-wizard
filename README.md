# Robinhood Wizard

An extensible, AI-powered stock-trading agent framework. Describe a strategy in plain
language; the agent researches the market, news, and sentiment, then proposes a trade
plan that runs in DryRun, Human-Approval, or Autonomous mode — always inside
per-strategy guardrails. Equities and ETFs only.

> **DISCLAIMER: Not financial advice. No warranty. Use at your own risk. The authors are not liable for any financial loss.**
> This software can place real trades with real money. You are solely responsible for any use.

## Status

Early development. See `docs/superpowers/specs/` for the design and
`docs/superpowers/plans/` for implementation plans.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A Robinhood **Agentic Trading** account (opened on desktop) authorized for the agent.

## Setup

```bash
uv sync
cp config.example.yaml ~/.rh-wizard/config.yaml   # then edit
uv run wizard auth login                           # one-time browser consent
uv run wizard accounts                             # verify the connection
```

Tokens and your local database live under `~/.rh-wizard/` and are never committed.

## License

MIT — see [LICENSE](LICENSE).
