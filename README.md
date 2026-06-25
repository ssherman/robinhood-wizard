# Robinhood Wizard

An extensible, AI-powered stock-trading agent framework. Describe a strategy in plain
language; the agent reconciles your live portfolio, pulls market data, researches the
candidates with an LLM, and proposes a trade plan — every proposed trade is independently
vetted by a deterministic risk engine. Equities and ETFs only.

> **DISCLAIMER: Not financial advice. No warranty. Use at your own risk. The authors are not liable for any financial loss.**
> This software is designed to eventually place real trades with real money. You are solely responsible for any use.

## Status

Actively developed. **What works today (Phases 0–4c):**

- **Authentication** to a Robinhood Agentic Trading account (browser consent → cached, auto-refreshed token).
- **Read-only portfolio + history** — reconcile live holdings, sync order history into a local journal.
- **Market data** — quotes + fundamentals for any symbols.
- **The trading cycle** — `wizard run <strategy>` runs the full pipeline: reconcile → resolve
  signals → **LLM research** → **LLM plan** → **risk vet** → journal.
- **Real LLM brain** — research and planning are done by an LLM (OpenAI, via the Strands
  Agents SDK) producing schema-validated structured output.
- **Natural-language strategy compiler** — `wizard compile <id> --text "..."` turns a plain
  description into a reviewable strategy YAML, using the LLM + web search to suggest a
  candidate universe (with citations). You review/edit the file, then `wizard run <id>`.

**DryRun only.** There is **no order-execution path anywhere in the codebase yet** — `run`
proposes and vets a plan, then stops. The risk engine is the hard gate and nothing can
place an order. Live execution (Human-Approval / Autonomous modes) is a future phase.

## How it works

A single **cycle** (`wizard run <strategy>`) executes a fixed, auditable pipeline. Each
stage has one job, and a failure in any stage aborts the cycle cleanly and journals the
abort rather than crashing or trading on bad state:

```
 strategy.yaml
      │
      ▼
┌─────────────┐   broker is ground truth (never trusts local state)
│ 1 RECONCILE │   live holdings + cash + buying power  ─── fail ─▶ abort
└─────────────┘
      ▼
┌─────────────┐   universe = strategy.universe ∪ current holdings
│ 2 RESOLVE   │   fetch quotes + fundamentals for the needed signals
└─────────────┘   (degrades and reports gaps; never raises)
      ▼
┌─────────────┐   LLM analyst: which candidates fit the thesis?
│ 3 RESEARCH  │   → ResearchReport (candidates, theses, conviction)  ─── fail ─▶ abort
└─────────────┘
      ▼
┌─────────────┐   LLM planner: turn research into limit orders
│ 4 PLAN      │   → TradePlan (buy/sell intents)  ─── fail ─▶ abort
└─────────────┘
      ▼
┌─────────────┐   DETERMINISTIC, un-bypassable gate. Vets every intent
│ 5 RISK VET  │   against the *resolved* market price: position size,
└─────────────┘   cash reserve, liquidity, slippage → approved / rejected
      ▼
┌─────────────┐   DryRun: NO execution. Record run + vetted plan to the
│ 6 JOURNAL   │   local SQLite journal for audit.
└─────────────┘
```

### Design principles

- **The risk engine is the boundary, not the LLM.** `risk/engine.py:vet()` is a pure
  function with no I/O. It re-checks every intent against the price the data layer
  *resolved* — so even a hallucinated `limit_price` from the LLM can't bypass a guardrail.
- **The LLM sits behind a narrow seam.** Research and planning depend only on a
  `StructuredLlm` Protocol (`generate(output_model, prompt, system) -> T`). Only one class
  (`llm/strands_llm.py`) imports the SDK. This keeps the brain provider-agnostic and lets
  the whole pipeline be unit-tested offline with a fake LLM — no network, no API keys.
- **Provider-agnostic.** `llm/provider.py` maps your config to a model. OpenAI is wired
  today; Anthropic/Bedrock are declared seams. Structured output is validated against the
  pydantic models, with **retry-then-abort** on malformed output.
- **Broker is ground truth.** Holdings are always reconciled live; local state is an audit
  log, never a source of truth for what you own.
- **Money is exact.** All prices and quantities are `Decimal`, never `float`.

### Layout

| Path | Responsibility |
|------|----------------|
| `auth/`, `broker/` | OAuth + token cache; Robinhood Agentic MCP client |
| `data/` | `DataSource` Protocol + `SignalResolver` (degrade-and-report) |
| `research/`, `planning/` | `Researcher` / `Planner` Protocols + LLM implementations (and offline stubs) |
| `llm/` | `StructuredLlm` seam, `RetryingLlm`, Strands adapter, provider builder |
| `risk/` | Pure risk engine (`vet`) + policy layering (defaults → ceiling → overrides) |
| `core/cycle.py` | The pipeline above (`run_cycle`) — brain-agnostic |
| `memory/` | Reconciliation + SQLite journal (`runs`, `plan_intents`, `trades`) |
| `models/` | Pydantic models for every stage's input/output |
| `cli/` | The `wizard` command surface (Typer + Rich) |

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A Robinhood **Agentic Trading** account (opened on desktop) authorized for the agent.
- An **OpenAI API key** (only needed for `wizard run` — the read-only commands don't use the LLM).

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Configuration (model provider, OAuth redirect, risk defaults)
mkdir -p ~/.rh-wizard
cp config.example.yaml ~/.rh-wizard/config.yaml      # then edit if desired

# 3. OpenAI key for the research/plan LLM (separate from Robinhood)
cp .env.example .env                                  # then set OPENAI_API_KEY=sk-...

# 4. One-time Robinhood browser consent
uv run wizard auth login

# 5. Verify the connection
uv run wizard accounts
```

Everything personal — tokens, your config, and the local database — lives under
`~/.rh-wizard/` and is never committed. The OpenAI key lives in a local `.env`, also never
committed.

> **Note on the OpenAI key:** the app reads `OPENAI_API_KEY` from the **process
> environment** and does *not* auto-load `.env`. The read-only commands ignore it entirely.
> For `wizard run`, either load `.env` via uv (`uv run --env-file .env wizard run ...`, shown
> below) or `export OPENAI_API_KEY=sk-...` in your shell first.

## Usage

### Read-only commands (no LLM, no orders)

```bash
uv run wizard accounts                 # list your agentic account(s)
uv run wizard positions                # reconcile live holdings: qty, cost, price, P/L, cash
uv run wizard history --limit 50       # sync + show recent order history
uv run wizard history --since 2026-01-01
uv run wizard data AAPL MSFT NVDA      # quotes + fundamentals for these symbols
```

All output masks account numbers to the last 4 characters. These commands place or cancel
nothing.

### Compiling a strategy from natural language

Instead of hand-writing the YAML, describe the strategy in prose and let the agent draft it
(name, thesis, a **web-search-suggested** candidate universe with citations, and the signals
to resolve). It writes `~/.rh-wizard/strategies/<id>.yaml` — **review and edit it**, then run
it. Because it uses the LLM + web search, provide the OpenAI key (it never touches the broker
and places no orders):

```bash
# From an inline description:
uv run --env-file .env wizard compile ai-large-cap \
  --text "Large-cap AI names with reasonable valuations; a few high-conviction picks."

# …or from a file:
uv run --env-file .env wizard compile ai-large-cap --file thesis.txt

uv run wizard strategies            # the new id now appears
# review ~/.rh-wizard/strategies/ai-large-cap.yaml, then:
uv run --env-file .env wizard run ai-large-cap
```

The suggested tickers are LLM web-search suggestions, not vetted picks — review them before
running. Re-compiling an existing id requires `--force`. The compiler never sets
`risk_overrides`; risk always comes from your global config (and any `risk_ceiling`).

### Running a strategy (the DryRun cycle)

1. **Write a strategy** as YAML in `~/.rh-wizard/strategies/`. Start from the example:

   ```bash
   mkdir -p ~/.rh-wizard/strategies
   cp strategies.example/sample-momentum.yaml ~/.rh-wizard/strategies/
   uv run wizard strategies                # lists available strategy ids
   ```

2. **Run one cycle.** Because `run` uses the LLM, provide the OpenAI key:

   ```bash
   uv run --env-file .env wizard run sample-momentum
   ```

The cycle reconciles your portfolio, resolves market data, asks the LLM to research the
universe and propose a plan, vets every intent through the risk engine, and prints the
result. **No orders are placed.** Example output:

```
Run 8db4… — strategy 'sample-momentum' — mode dryrun — completed
Cash: $3,000.00   Total value: -
Research: MSFT is the strongest fit — mega-cap tech with the most reasonable valuation;
NVDA fits but at a higher P/E; AAPL excluded as its P/E is the highest in the universe.
Rejected:
  buy MSFT: would exceed max position 20% of portfolio
  buy NVDA: would exceed max position 20% of portfolio
DryRun — no orders placed.
```

Here the LLM did genuine research over live fundamentals and proposed buys, and the **risk
engine rejected them on the merits** (a single position would breach the 20% max-position
guardrail on a small account). Approved intents render in a "Proposed trades" table. Every
run — approved, rejected, or aborted — is recorded in `~/.rh-wizard/wizard.db`.

### Strategy file format

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Stable id; **must match the YAML filename stem** (`run` uses it) |
| `name` | yes | Human-readable name |
| `intent` | no | Free-text thesis handed to the research LLM |
| `universe` | no | Explicit candidate tickers the agent may consider |
| `signals_needed` | no | Market signals to resolve (`price`, `average_volume`, `market_cap`, `pe_ratio`, `pb_ratio`, `sector`, `industry`, `week_52_high`, `week_52_low`, `dividend_yield`) |
| `cadence` | no | Hint only in v1 (e.g. `weekly`) |
| `risk_overrides` | no | Per-strategy risk tightening, merged onto the global defaults |

```yaml
id: sample-momentum
name: Sample Momentum (example)
intent: >
  Prefer large-cap technology names with reasonable valuations.
universe: [AAPL, MSFT, NVDA]
signals_needed: [price, average_volume, market_cap, pe_ratio]
cadence: weekly
risk_overrides:
  max_position_pct: 15
```

> `wizard compile` can *suggest* a `universe` from a prose theme (web-search-backed) for you
> to review. Fully automatic, per-cycle theme→ticker discovery (so `intent` alone drives every
> run) is a planned phase.

## Risk guardrails

The risk engine enforces these on every cycle. Global defaults live in
`~/.rh-wizard/config.yaml`; a strategy may *tighten* them via `risk_overrides`, bounded by
an optional global `risk_ceiling`.

| Guardrail | Default | Meaning |
|-----------|---------|---------|
| `max_position_pct` | 20 | Max % of portfolio in any single position |
| `cash_reserve_pct` | 10 | Min % of portfolio kept as cash |
| `max_trades_per_cycle` | 5 | Max number of intents approved per cycle |
| `max_deploy_pct_per_cycle` | 30 | Max % of portfolio deployed (bought) per cycle |
| `slippage_band_pct` | 0.5 | Max % a limit price may sit off the resolved market price |
| `min_price` | 5 | Liquidity floor: minimum share price |
| `min_avg_volume` | 1,000,000 | Liquidity floor: minimum average daily volume |
| `min_market_cap` | 1,000,000,000 | Liquidity floor: minimum market cap |
| `drawdown_kill_switch_pct` | 15 | Halt threshold (carried now; enforced in a later phase) |

Sells are exempt from buy-only guardrails. Buy-side liquidity/size/slippage rules are
strictly enforced.

## Security & secrets

- **Two independent credentials:** the Robinhood OAuth token (in `~/.rh-wizard/tokens.json`)
  and the LLM `OPENAI_API_KEY` (in `.env`). Neither is ever logged, journaled, or rendered;
  log output is run through a redaction filter.
- The trading account is **detected at runtime** via `agentic_allowed` from the broker — no
  account number is hardcoded.
- DryRun-only: no code path can place or cancel an order.

## Development

```bash
uv run pytest                    # full suite (offline; no network/LLM/broker)
uv run ruff check .              # lint
uv run ruff format --check .     # formatting (CI enforces both ruff steps)
```

Unit tests use fakes (`FakeStructuredLlm`, `FakeBroker`, `FakeDataSource`) — they never hit
the network, an LLM, or the broker. An opt-in live DryRun integration test exists behind
`RH_WIZARD_LIVE=1` (and requires an OpenAI key + cached Robinhood token):

```bash
RH_WIZARD_LIVE=1 uv run --env-file .env pytest tests/integration -v -s
```

Design docs live in `docs/superpowers/specs/`; per-phase implementation plans in
`docs/superpowers/plans/`.

## Roadmap

- **Done:** scaffold/auth (0) · read-only portfolio + journal (1) · risk engine (2) · data
  layer (3) · DryRun cycle skeleton (4a) · LLM research + plan (4b-1) · web/news search
  (4b-2) · **natural-language strategy compiler (4c)**.
- **Next:** theme→ticker universe discovery · order execution with Human-Approval /
  Autonomous modes and kill-switch enforcement.

## License

MIT — see [LICENSE](LICENSE).
