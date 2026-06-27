# Robinhood Wizard

An extensible, AI-powered stock-trading agent framework. Describe a strategy in plain
language; the agent reconciles your live portfolio, pulls market data, researches the
candidates with an LLM, and proposes a trade plan — every proposed trade is independently
vetted by a deterministic risk engine. Equities and ETFs only.

> **DISCLAIMER: Not financial advice. No warranty. Use at your own risk. The authors are not liable for any financial loss.**
> This software is designed to eventually place real trades with real money. You are solely responsible for any use.

## Status

Actively developed. **What works today (Phases 0–5):**

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
- **Dynamic universe discovery** — a strategy with `discover: true` discovers fresh candidate
  tickers from its `intent` each cycle (web-search-backed), unioned with any hand-picked
  `universe` and your holdings. Write a thesis, the agent finds the names.
- **Allocation buckets + allocation-aware planning** — a strategy can split investable capital
  into named themes, each with a target % (e.g. 40% AI, 20% energy). The LLM picks the tickers
  and their relative weights per bucket; a deterministic allocator sizes positions (whole or
  fractional shares) to hit the targets and trims/buys to rebalance within a drift band; the
  risk engine vets every order. See **Bucketed strategies** below.
- **Order execution (Human-Approval mode)** — `wizard run <id> --execute` runs the full cycle
  and, after you type `yes` to confirm, places the approved orders on your agentic Robinhood
  account. The risk engine vets every order before any placement; a failure halts and reports.

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

If the description assigns target percentages to themes (e.g. "20% rare-earth funds, 40% AI,
…"), `wizard compile` automatically produces a **bucketed** strategy — one bucket per theme
with its target %, each bucket's web-searched tickers frozen as its reviewable `universe`
(`discover: false`). Flip a bucket to `discover: true` in the generated YAML for dynamic
discovery each cycle. See the **Bucketed strategies** section below for run-time behavior.

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

To let the agent assemble the universe itself, set `discover: true` and leave `universe`
empty (or list a few core names to keep alongside the discovered ones):

```yaml
id: ai-discovered
name: Discovered AI
intent: Large-cap AI names with reasonable valuations.
universe: []            # discovery fills this each cycle
signals_needed: [price, average_volume, market_cap, pe_ratio]
discover: true
```

```bash
uv run --env-file .env wizard run ai-discovered
```

The cycle discovers candidates from `intent`, resolves their live data, researches and proposes
a vetted plan — printing a "Discovered universe" line with citations. If discovery fails the
cycle degrades (it proceeds with your explicit `universe` + holdings and notes the failure),
and the risk engine still vets every proposed trade. **No orders are placed.** Discovery uses the
web-search LLM, so provide your OpenAI key (e.g. via `--env-file .env`).

### Placing real orders (HumanApproval)

**DryRun is the default.** `wizard run <id>` never places an order — it proposes and vets a
plan, then stops. To actually place orders, add `--execute`:

```bash
uv run --env-file .env wizard run sample-momentum --execute
```

The cycle runs the full pipeline (reconcile → research → plan → risk vet) exactly as in
DryRun. After the vetted plan is shown, you are prompted to type `yes` to confirm. No bypass
exists — anything other than the exact word `yes` cancels execution.

**Order types by intent:**

| Intent | Order type | Notes |
|--------|-----------|-------|
| Whole-share buy or sell | Limit order | Price-protected — the limit price comes from the risk-vetted price |
| Fractional/notional buy or sell | Market order | Regular hours only — run during market hours |

**Safety guarantees:**

- Orders go **only to your agentic account** — the account is detected at runtime from the
  broker's `agentic_allowed` flag; nothing is hardcoded.
- The risk engine vets every order **before** any placement. An order rejected by the risk
  engine is never submitted.
- On a **place failure** (broker error, network issue, etc.) execution halts immediately and
  reports the failure. Remaining approved orders in the same cycle are not attempted.
- Every order — placed, skipped, or failed — is journaled to `~/.rh-wizard/wizard.db` for
  audit. Each order carries a stable `ref_id` for idempotency.

### Strategy file format

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Stable id; **must match the YAML filename stem** (`run` uses it) |
| `name` | yes | Human-readable name |
| `intent` | no | Free-text thesis handed to the research LLM |
| `universe` | no | Explicit candidate tickers the agent may consider |
| `discover` | no | If `true`, discover candidate tickers from `intent` each cycle (web-search-backed) and union them with `universe` + holdings. Default `false` |
| `max_candidates` | no | Cap on discovered candidates per cycle (default `20`) |
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

> Two ways to get a universe from a theme: `wizard compile` *suggests* a `universe` once for
> you to review/freeze; `discover: true` discovers one *dynamically every cycle* from `intent`.
> Use either, or both (a reviewed core list plus live discovery around it). For target-percentage
> allocation across themes, see **Bucketed strategies** below.

### Bucketed strategies

A bucketed strategy divides your investable capital into named themes, each with a target
percentage. The LLM recommends which tickers fit each bucket and their relative weights; a
deterministic allocator sizes the positions to hit the targets; the risk engine vets every
proposed order. Buckets are **mutually exclusive** with a flat top-level `universe` or
`discover` key — use one model or the other per strategy file.

```yaml
buckets:
  - id: ai               # stable id for this bucket (used in journaling)
    name: AI             # display name
    target_pct: 40       # target % of investable capital
    intent: Large-cap AI and semiconductor leaders with durable demand.
    discover: true        # discover candidate tickers for this theme each cycle
    max_candidates: 15
  - id: energy
    name: Energy
    target_pct: 20
    intent: Large-cap energy producers with strong free cash flow.
    universe: [XOM, CVX]  # or list tickers explicitly instead of discovering
  - id: broad
    name: Broad market
    target_pct: 20
    universe: [VOO]
# Targets sum to 80%; the remaining 20% of investable stays as extra cash.
```

Targets are expressed as **% of investable capital** (portfolio value minus the configured
cash reserve). They need not sum to 100 — any gap becomes additional cash. Each bucket may
use `universe`, `discover: true`, or both.

Three per-strategy dials control rebalance behavior (all shown with their defaults):

| Field | Default | Meaning |
|-------|---------|---------|
| `allow_fractional` | `true` | Size positions fractionally when Robinhood marks the symbol as fractionable; automatically degrades to whole-share sizing for symbols that do not support it |
| `rebalance_mode` | `full` | `full` = buy under-weight buckets *and* sell-to-trim over-weight ones; `buy_only` = never sells |
| `rebalance_band_pct` | `5` | Only rebalance a bucket when its current allocation drifts more than this many percentage points from its target |

The rebalance band **decouples how often you run the cycle from how often it actually trades**.
With a 5-point band and weekly cadence, a bucket that drifts only 3 points off target is
left alone that cycle — this prevents churning on normal market noise.

Copy the annotated example and run one cycle (like `run`, it uses the LLM, so provide the
OpenAI key):

```bash
cp strategies.example/sample-buckets.yaml ~/.rh-wizard/strategies/
uv run --env-file .env wizard run sample-buckets
```

The cycle discovers/recommends per bucket, the allocator sizes positions to the targets, and
the risk engine vets every order. You'll see an **Allocation** table alongside the proposed
trades — for example, on a first run with no existing holdings:

```
Run 7f3a… — strategy 'sample-buckets' — mode dryrun — completed
Cash: $3,000.00   Total value: $3,000.00
        Allocation (target vs current per bucket)
┌──────────────┬────────┬─────────┬─────────┬───────┬────────┐
│ Bucket       │ Target │ Current │   Drift │ Band? │ Action │
├──────────────┼────────┼─────────┼─────────┼───────┼────────┤
│ AI           │ 40.00% │  0.00%  │ -40.00% │  no   │ buy    │
│ Energy       │ 20.00% │  0.00%  │ -20.00% │  no   │ buy    │
│ Broad market │ 20.00% │  0.00%  │ -20.00% │  no   │ buy    │
└──────────────┴────────┴─────────┴─────────┴───────┴────────┘
Proposed trades (DryRun — approved)
  buy NVDA …   buy XOM …   buy VOO …
Rejected:
  buy MSFT: would exceed per-cycle deploy cap of 30%
DryRun — no orders placed.
```

> **Deployment ramps over several cycles.** With the conservative defaults
> (`max_deploy_pct_per_cycle` 30%, `max_position_pct` 20%, `max_trades_per_cycle` 5), a fresh
> bucketed strategy whose targets sum to ~80% won't buy everything at once — the Allocation
> table shows the targets while the risk engine paces the actual buys. Re-run on your cadence;
> each cycle closes the drift until the band is satisfied.

See `strategies.example/sample-buckets.yaml` for a complete annotated example to copy and
adapt.

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
- Real orders require explicit `--execute` plus a typed `yes` confirmation — DryRun (the
  default) has no order-placement path.

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
  (4b-2) · natural-language strategy compiler (4c) · dynamic universe discovery (4d) ·
  allocation buckets + allocation-aware planning (4e) ·
  **order execution — Human-Approval mode (5)**.
- **Next:** Autonomous mode (scheduled, unattended execution) + kill-switch enforcement.

## License

MIT — see [LICENSE](LICENSE).
