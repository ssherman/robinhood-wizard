# Robinhood Wizard — Design Spec

- **Date:** 2026-06-21
- **Status:** Approved (design) — pending implementation plan
- **Author:** Shane (with Claude)

## 1. Overview

Robinhood Wizard is an extensible, AI-powered stock-trading agent framework. A user
specifies a **strategy** in natural language; the agent researches industries, stocks,
news, and online sentiment using market data and external sources, then produces a
**trade plan** of proposed buys/sells. Depending on the configured execution mode, the
plan is either shown for approval or executed automatically — always within deterministic,
per-strategy guardrails.

The system trades **equities and ETFs only** through Robinhood's official **Agentic
Trading MCP server**. It starts as a single-user CLI app with a clean path to scheduled
autonomy and, later, a web app.

The end goal is **full autonomy**; the first milestone is **human-approved** trading. The
architecture is designed so autonomy is a configuration change, not a rewrite.

## 2. Goals & Non-Goals

### Goals (v1)
- Author strategies in natural language, compiled into a validated structured form.
- Research using Robinhood market data + general web search/sentiment.
- Generate an auditable **trade plan** with reasoning for every proposed trade.
- Three execution modes: **DryRun**, **HumanApproval**, **Autonomous** — sharing one pipeline.
- Per-strategy **risk guardrails** that the LLM cannot bypass.
- Persistent **journal/memory** so the agent is context-aware (recent trades, % return, rationale).
- Extensible plugin seams for new strategies, data sources, and memory backends.

### Non-Goals (v1 — YAGNI, but seams left clean)
- Options and margin trading.
- Multi-user / web app / per-user auth.
- Vector / semantic memory.
- Backtesting engine.
- Real-time price streaming / intraday high-frequency reactions.
- Tax-lot optimization.

## 3. Key Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Autonomy model | "Plan" is the central artifact; execution mode (DryRun / HumanApproval / Autonomous) is a thin policy layer. First milestone = HumanApproval; end goal = Autonomous. |
| 2 | Strategy specification | **Hybrid**: natural-language intent → validated structured `Strategy` object (with embedded `RiskPolicy`). Code-module strategies are a later extension point. |
| 3 | Data sources | Pluggable `DataSource` interface; sources **declare the signals they provide**, strategies **declare the signals they need**. v1 = Robinhood MCP (price/valuation/earnings) + web search/fetch (news/sentiment). EDGAR + AlphaVantage are later plugins for deep fundamentals. |
| 4 | Asset scope | Equities + ETFs only. Options out of scope, behind the `OrderExecutor` interface. |
| 5 | Cadence | Single idempotent "run" cycle; on-demand CLI for v1; market-aware scheduler for autonomy. Long-horizon/fundamental signals → daily/weekly is sufficient; no streaming. |
| 6 | Memory | `Journal` interface; v1 = live broker reconciliation + SQLite journal. Vector backend deferred behind the same interface. |
| 7 | Tech stack | Python 3.12, **Strands Agents SDK** (MCP-native, model-agnostic), provider-agnostic model config. Deps via **uv**; lint/format **ruff**; tests **pytest**. |
| 8 | Architecture style | **Approach 3 — Hybrid**: deterministic skeleton owns control flow, guardrails, and execution; the LLM runs loose only inside research & plan-generation. |
| 9 | Guardrails | Fully **per-strategy** `RiskPolicy` (overrides ∘ global defaults), with a small always-on **integrity floor** (reconciliation, audit log, review-before-place) and an optional global **hard-ceiling** bounding strategy overrides. |
| 10 | Broker auth | Robinhood MCP uses **OAuth 2.1** (PKCE + dynamic client registration). Browser consent once; refresh token cached to disk; silent refresh thereafter. |
| 11 | Distribution | Intended to be **open-sourced under the MIT license**. Drives secrets hygiene, a financial/legal disclaimer, no personal config in-repo, and community/CI files (see §19). |

## 4. Guiding Principles

1. **Deterministic safety envelope, agentic research core.** The LLM is creative where
   judgment helps and *structurally incapable* of moving money on its own.
2. **The plan is the central artifact.** Execution mode wraps the same plan.
3. **The broker is ground truth.** Every cycle reconciles against live Robinhood state;
   we never trust our own memory for "what we hold."
4. **Everything pluggable behind interfaces:** strategies, data sources, memory, model
   provider, order executor.

## 5. Architecture — Components

| Component | Responsibility | Key seam |
|---|---|---|
| **CLI** (`cli/`) | Commands: `run`, `plan` (dry-run), `strategies`, `positions`, `history`, `auth login`, `approve` | Typer |
| **Cycle orchestrator** (`core/`) | Deterministic skeleton — runs fixed pipeline stages in order | — |
| **Strategy** (`strategies/`) | `Strategy` model + `StrategyCompiler` (NL → structured) + `StrategyRegistry` (YAML files; code-module extension later) | `Strategy` |
| **Data layer** (`data/`) | `DataSource` interface (declares provided signals); `RobinhoodDataSource`, `WebResearchDataSource`; `SignalResolver` routes needed → provided signals into a `MarketContext` | `DataSource` |
| **Research agent** (`research/`) | Strands agent investigates → structured `ResearchReport`. Cannot place orders. | — |
| **Plan generator** (`planning/`) | ResearchReport + portfolio + strategy → `TradePlan` (proposed `TradeIntent`s). Structured-output-validated. | — |
| **Risk engine** (`risk/`) | **Pure deterministic code.** Vets plan vs. effective `RiskPolicy` → `VettedPlan`. LLM cannot bypass. | `RiskPolicy` |
| **Execution** (`execution/`) | `ExecutionPolicy` (DryRun/HumanApproval/Autonomous) + `ApprovalGate` + `OrderExecutor` → `RobinhoodOrderExecutor` (always `review_equity_order` → `place_equity_order`) | `OrderExecutor` |
| **Memory/Journal** (`memory/`) | `Journal` (SQLite) records plans/decisions/rationale/orders/outcomes; `PortfolioState` (live reconciliation); `PerformanceTracker` (% return, high-water mark) | `Journal` |
| **Auth** (`auth/`) | OAuth 2.1 to Robinhood MCP; `TokenStorage` to disk; silent refresh; wraps MCP SDK `OAuthClientProvider` | `TokenStorage` |
| **Broker adapter** (`broker/`) | Single place that knows MCP — wraps Strands `MCPClient` → Robinhood, typed methods | — |
| **LLM provider** (`llm/`) | Strands model config, provider-agnostic; choose provider/model per run | — |
| **Config** (`config/`) | Global `config.yaml`: default `RiskPolicy`, global hard-ceiling, model provider, paths | — |

## 6. Core Interfaces (indicative signatures — finalized during implementation)

```python
class DataSource(Protocol):
    name: str
    def provides(self) -> set[Signal]: ...
    def fetch(self, symbols: list[str], signals: set[Signal]) -> MarketData: ...

class OrderExecutor(Protocol):
    def review(self, intent: TradeIntent) -> ReviewResult: ...
    def place(self, intent: TradeIntent) -> OrderResult: ...

class Journal(Protocol):
    def record_run(self, run: CycleRun) -> None: ...
    def record_plan(self, plan: TradePlan, vetted: VettedPlan) -> None: ...
    def record_order(self, order: OrderResult) -> None: ...
    def recent_trades(self, limit: int) -> list[TradeRecord]: ...

class RiskEngine:  # pure, no I/O
    def vet(self, plan: TradePlan, policy: RiskPolicy,
            portfolio: PortfolioState) -> VettedPlan: ...
```

## 7. Key Data Models (Pydantic)

- **`Strategy`** — id, name, natural-language intent, structured fields (universe definition,
  signals needed, cadence hint), embedded `RiskPolicy` overrides.
- **`RiskPolicy`** — max position % of portfolio, cash-reserve %, max trades/cycle, per-cycle
  spend cap, slippage band, liquidity floor (min price / min avg volume / min market cap),
  drawdown kill-switch threshold. Effective policy = strategy overrides merged onto global defaults.
- **`MarketContext`** — resolved market data + news/sentiment for the candidate universe.
- **`ResearchReport`** — findings, candidate tickers, theses, conviction (structured agent output).
- **`TradeIntent`** — side (buy/sell), symbol, target qty or $ amount, limit price, rationale, confidence.
- **`TradePlan`** — ordered list of `TradeIntent`s + overall rationale.
- **`VettedPlan`** — approved intents, adjusted intents, rejected intents (with reasons).
- **`PortfolioState`** — live positions, cost basis, cash, buying power, % return (from broker).
- **`CycleRun`** — run_id, strategy, mode, timestamps, stage outcomes (for audit/idempotency).

## 8. The Trading Cycle (deterministic skeleton — `wizard run <strategy>`)

```
 1. Load strategy ............... Strategy + effective RiskPolicy (overrides ∘ defaults)
 2. Connect broker ............. MCP client; refresh OAuth token (no browser)
 3. RECONCILE  [hard] .......... pull live positions/cash/cost-basis → PortfolioState
 4. Kill-switch check [hard] ... update high-water mark; HALT if drawdown ≥ threshold
 5. Resolve signals ............ SignalResolver fetches MarketContext (Robinhood + web)
 6. RESEARCH  [agentic] ........ Strands agent investigates → ResearchReport
 7. PLAN  [agentic] ............ Plan generator → TradePlan (proposed intents)
 8. RISK ENGINE [hard/pure] .... vet & adjust → VettedPlan (approved/rejected + reasons)
 9. Execution policy:
       DryRun ........ render plan + reasoning, STOP (no orders)
       HumanApproval . ApprovalGate renders plan → user approves (whole-plan or per-trade)
       Autonomous .... proceed within rails
10. Execute ................... per approved intent: review_equity_order → place_equity_order
11. JOURNAL [hard] ............ persist plan, decisions, rationale, orders, outcomes (SQLite + audit log)
12. Summary ................... render results to user
```

Steps **3, 4, 8, 10, 11** are deterministic and non-skippable (the integrity floor lives here).
Steps **6–7** are where the LLM runs loose — its only output is a *proposed* plan that must
survive the risk engine. New strategies **default to DryRun** until explicitly promoted.

## 9. Guardrails / Risk Policy

- **Per-strategy `RiskPolicy`** overrides global defaults. Conservative defaults tuned for a
  ~$3,000 account: max 20% per position, ≥10% cash reserve, ≤5 trades/cycle, ≤30% portfolio
  deployed per cycle, limit orders with ≤0.5% slippage band, liquidity floor (price ≥ $5,
  avg volume ≥ 1M shares, market cap ≥ $1B), drawdown kill-switch at 15% off high-water mark.
- **Integrity floor (always on, every strategy):** broker reconciliation, immutable audit log,
  review-before-place. These are correctness guarantees, not risk dials.
- **Optional global hard-ceiling:** bounds what any strategy override may set (e.g. a typo
  can't set max-position to 100% or disable the kill-switch). Configurable; can be disabled.
- **Account-level:** trades execute only in Robinhood's dedicated, separately-funded **Agentic
  account** — itself a structural guardrail walling the agent off from primary holdings.

## 10. Execution Modes

- **DryRun** — produce and render the plan; never place orders. Default for new strategies.
- **HumanApproval** — render the vetted plan; user approves whole-plan or per-trade before execution.
- **Autonomous** — execute approved intents automatically, within rails, on a schedule.

## 11. Data Sources & Signal Resolution

- Robinhood MCP supplies: real-time quotes, fundamentals (market cap, P/E, P/B, shares, float,
  52-wk range, avg volume, dividends, sector/industry), historicals (OHLCV, adjustable),
  earnings calendar/results, technical scans.
- Robinhood does **not** supply deep financial-statement factors (EV/EBIT, FCF yield,
  Debt/EBITDA, ROIC, Piotroski F-score, revenue trends) — these require **EDGAR** (free, full
  financials) and/or **AlphaVantage**, added later as `DataSource` plugins.
- Web search/fetch supplies news + rough sentiment with no extra API keys for v1.
- `SignalResolver` maps each signal a strategy needs to a source that provides it, and merges
  results into a `MarketContext`.

## 12. Auth / MCP Connection

- Endpoint: `https://agent.robinhood.com/mcp/trading`, **Streamable HTTP** transport.
- **OAuth 2.1** (authorization-code + PKCE + dynamic client registration). Access tokens last
  ~4 days; a refresh token enables silent renewal.
- Flow: browser consent once via `wizard auth login`; persist refresh token to disk
  (`~/.rh-wizard/tokens.json`) via a `TokenStorage` implementation; the MCP SDK's
  `OAuthClientProvider` refreshes silently on subsequent headless runs.
- Strands `MCPClient` is constructed with the OAuth-configured Streamable-HTTP transport.

## 13. Error Handling — *fail safe, never trade blind or twice*

| Failure | Behavior |
|---|---|
| OAuth refresh fails | Abort before trading; prompt `wizard auth login`. |
| Reconciliation fails | **Abort the cycle** — never trade without ground-truth state (anti-double-buy guard). |
| MCP data call timeout/error | Retry with backoff; if still failing, abort cycle cleanly. |
| `review_equity_order` rejects an intent | Skip that intent, log reason, continue the rest. |
| `place_equity_order` fails mid-plan | Journal what executed; re-reconcile; report clearly. No silent partials. |
| Agent returns invalid structured output | Retry N times with schema feedback; if still invalid, abort cycle (no valid plan ⇒ no trades). |
| Kill-switch tripped | Halt autonomous trading; require explicit human acknowledgement to resume. |
| Crash / re-run | Each cycle has a `run_id`; recovery reconciles against the broker so a re-run can't double-buy. |
| Rate limits (undocumented) | Backoff; cache market data within a cycle; treat 429s as soft failures. |

## 14. Testing — the risk engine is the crown jewel

- **Unit (deterministic, no network/LLM):** exhaustive table-driven tests for **every** risk
  guardrail; strategy compiler/validation; signal-resolver routing; performance & high-water-mark math.
- **Fakes** (`FakeBroker`, `FakeDataSource`, `FakeExecutor`, stubbed agent returning canned
  `ResearchReport`/`TradePlan`) → run the entire cycle offline, no Robinhood, no LLM cost.
- **Execution-mode tests:** DryRun never calls the executor; HumanApproval blocks until approval;
  Autonomous respects all rails.
- **Safety property tests:** no order ever exceeds the effective RiskPolicy; no trade when
  reconciliation fails; kill-switch always halts.
- **Integration (opt-in, env-gated):** against the real MCP but read-only / `review`-without-`place`.

## 15. Project Structure

```
robinhood-wizard/
  pyproject.toml          # uv-managed
  uv.lock
  src/rh_wizard/
    cli/         core/        config/      strategies/
    data/        research/     planning/    risk/
    execution/   memory/       broker/      auth/
    llm/         models/       # shared Pydantic models
  tests/  ( unit/  fakes/  integration/ )
  docs/superpowers/specs/
  ~/.rh-wizard/   # runtime: config.yaml, tokens.json, wizard.db, strategies/*.yaml
```

## 16. Tooling

- **uv** for dependency management and the Python toolchain (`pyproject.toml` + `uv.lock`).
- **Python 3.12.**
- **ruff** for lint + format.
- **pytest** for tests.
- Key deps: `strands-agents`, `mcp` (Python SDK), `pydantic`, `typer`, `httpx`, `rich` (CLI rendering).
  (Pin `mcp` carefully — see Open Risks re: API signature drift.)

## 17. Build Sequencing (drives the implementation plan)

- **Phase 0** — Scaffold, config, shared models, **auth** (prove Python→Robinhood-MCP with token refresh). *Riskiest unknown first.*
- **Phase 1** — Broker adapter + reconciliation + `PortfolioState` + `Journal` (read-only): `wizard positions`, `wizard history`.
- **Phase 2** — **Risk engine, pure and fully tested** — before any execution path exists.
- **Phase 3** — Data layer + `SignalResolver` (Robinhood + web).
- **Phase 4** — Research agent + plan generator → full **DryRun** cycle end-to-end (no real orders).
- **Phase 5** — Execution + `ApprovalGate` → **HumanApproval** mode → first real, human-approved trades. *(First-milestone goal.)*
- **Phase 6** — **Autonomous** mode + market-aware scheduler + kill-switch enforcement.
- **Later (post-v1):** EDGAR + AlphaVantage sources, vector/semantic memory, backtesting, web app.

## 18. Open Risks / Unknowns — Resolved Hands-On (Phase 0, 2026-06-22)

Pinned versions: `strands-agents 1.44.0` (confirmed latest), `mcp 1.28.0`. Verified live
against the real Robinhood Agentic MCP server under WSL2.

1. **MCP transport signature — RESOLVED.** `mcp` 1.28.0 uses
   `streamable_http_client(url, *, http_client=...)`; pass an `httpx.AsyncClient(auth=provider)`.
   The older `streamablehttp_client(headers=, auth=)` form is not used.
2. **OAuth `server_url` — RESOLVED.** Must be the **full `/mcp/trading` URL**, not the base
   host. Robinhood's protected-resource metadata advertises the full URL and the SDK validates
   the configured resource against it; the base host fails with `OAuthFlowError` (resource
   mismatch).
3. **OAuth handlers + headless/WSL flow — RESOLVED.** `OAuthClientProvider` requires **async**
   `redirect_handler(url) -> None` and `callback_handler() -> (code, state)`. Under WSL the
   browser cannot reach a localhost callback server, so we use a **paste-based** callback (user
   pastes the redirect URL). Dynamic client registration + PKCE + token exchange + on-disk
   token storage (`DiskTokenStorage`, 0600) all work; **silent refresh confirmed** (second run
   needs no browser). The `OAuthCallbackServer` localhost listener is currently unused.
4. **Strands tool-call API — RESOLVED.** `MCPClient.call_tool_sync(tool_use_id, name, arguments)`
   requires a `tool_use_id` and returns an `MCPToolResult` dict (`status`, `toolUseId`,
   `content[]` of `{text|json}`, optional `structuredContent`) — not the raw MCP payload. The
   `get_accounts` payload nests under `data.accounts`.
5. **Still open (later phases):** rate limits & scopes (undocumented; design backoff);
   token-refresh rotation and undocumented token fields (`mfa_code`, `backup_code`); a benign
   `"Session termination failed: 400"` warning on MCP context exit (Robinhood's terminate
   endpoint) — cosmetic, to be silenced; account numbers are not yet masked in user-facing
   output (the tool guide recommends masking all but the last 4 digits).

## 19. Open-Source Considerations

The project is intended to be released publicly under the **MIT license**. This is a design
constraint from day one, not a later cleanup:

- **License:** `MIT` (`LICENSE` file at repo root, copyright holder = the author).
- **Secrets hygiene (critical — this repo holds trading credentials):**
  - OAuth tokens, the SQLite DB, and any `.env` are gitignored and **never committed**.
  - Config and runtime state live in `~/.rh-wizard/`, never in the repo. A committed
    `config.example.yaml` / `.env.example` contains placeholders only.
  - **No credentials, account numbers, or PII are ever logged.** The audit log and journal
    must be safe to share — sensitive identifiers (account numbers, tokens) are redacted or
    omitted. A test asserts logs contain no secret-shaped values.
- **Financial / legal disclaimer (mandatory before others run it):** a prominent notice in the
  `README` and on first CLI run — *not financial advice, no warranty, use at your own risk, the
  authors are not liable for any financial loss.* The software places real trades.
- **No personal config baked in:** no hardcoded strategies, account specifics, or defaults
  tied to the author. Everything user-specific is user-provided.
- **Community & quality files:** `README` (setup, how to get a Robinhood Agentic account,
  OAuth flow, configuration), `CONTRIBUTING.md`, `SECURITY.md` (responsible disclosure — the
  project handles money and credentials), and `CODE_OF_CONDUCT.md` (optional).
- **CI:** GitHub Actions running `ruff` (lint + format check) and `pytest` on push/PR — also
  reinforces the clean, well-tested public interfaces the framework depends on.
- **Public API quality:** plugin seams (`Strategy`, `DataSource`, `OrderExecutor`, `Journal`)
  get docstrings and stable typed signatures, since third parties will extend them.

## 20. Future Roadmap (post-v1)

- EDGAR + AlphaVantage data sources for deep fundamental factor screens (Piotroski, ROIC, FCF
  yield, EV/EBIT, Debt/EBITDA, revenue trend).
- Vector/semantic memory (pgvector or Qdrant) behind the `Journal`/`Memory` interface.
- Backtesting engine over Robinhood historicals.
- Migration SQLite → Postgres for multi-user + vector.
- Web app front-end over the same core.
- Code-module strategies as a registered extension point.
- Options support behind the existing `OrderExecutor` interface (only if/when desired).
