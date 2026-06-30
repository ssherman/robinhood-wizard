# Research mode — detached account context + capital override (Design)

- **Date:** 2026-06-29
- **Status:** Approved design (pre-plan)
- **Depends on:** Phases 0–5 (all merged to main) and the bucket deploy-completeness change
  (PR #15). This sits on the **cycle reconcile boundary** and touches both the flat and bucketed
  paths uniformly (by construction — see §4).
- **Origin:** Shane wants to run a strategy *without* his own account's holdings biasing the
  result (e.g. to draft a plan for a friend, or to do open-ended research), and to supply the
  investable dollar amount as a parameter instead of reading it from his account.
- **Scope:** Two **composable** `wizard run` flags — `--capital N` (override the money) and
  `--ignore-holdings` (treat positions as empty). Either flag puts the run into a read-only,
  no-orders "research" posture.
- **Out of scope (YAGNI):**
  - Specifying *synthetic holdings* for a friend who already owns positions (only "empty" is
    supported; supplying a phantom portfolio is a separate, larger feature).
  - A fully offline mode with no Robinhood connection. Market data (quotes, fundamentals, and the
    `fractionable` signal via `get_equity_tradability`) still flows through the authenticated
    Robinhood MCP; there is no alternate data source in the codebase. Building one is out of scope.
  - Exporting the plan to a shareable file. The terminal render is sufficient for v1.

## 1. Why we're here

Today a cycle's entire view of "my situation" is the single `PortfolioState` produced by
`reconcile()` (`memory/portfolio.py:114`) and enriched by `enrich_with_quotes()`:

- `positions` — live holdings
- `cash` / `buying_power` — live money
- `account_number` — which account to act on

That one object then drives **everything downstream**: investable-capital sizing
(`allocation/engine.py:_portfolio_value`), rebalance/trim math (`_held_value`), the candidate
universe (held symbols are unioned in — `core/cycle.py:175-179`), the research/plan LLM context,
risk vetting, and execution. There is no way to run the pipeline against anything other than the
real, live account.

Two real use cases need a detached view:

1. **Draft a plan for a friend / open-ended research** — run the strategy as a clean slate so my
   existing holdings don't pollute the universe, the rebalance math, or the LLM's context.
2. **Size to a hypothetical amount** — "what would this strategy do with $10,000?" — without that
   number having to be my actual balance.

These compose: a friend's run is "clean slate **and** their dollar amount."

## 2. Invariants that bind (must stay true)

- **The pipeline downstream of reconcile is untouched.** Universe building, research, planning,
  the allocator, and risk `vet()` are not modified. They keep reading `PortfolioState`; we change
  only the `PortfolioState` they receive. This is the whole point of Approach 1 (§3).
- **`allocate()` / `vet()` stay pure and remain the sole cap authority.** No change to either.
- **A research run NEVER places an order.** Enforced at three independent layers (§6).
- **The broker is still ground truth for market data.** We still authenticate, still resolve the
  real `account_number`, and still fetch live quotes/fundamentals. We override only the
  *account-state* fields (`positions`, `cash`, `buying_power`), and only in-memory for this run.
- **DryRun stays the default.** Research mode is a stricter posture, not a new execution mode.
- **Money stays `Decimal`.** `--capital` is parsed to `Decimal` via `str()` to avoid binary-float
  drift, consistent with the codebase's money rule.

## 3. Approach (chosen)

**Override the `PortfolioState` immediately after `reconcile()`, before `enrich_with_quotes()`.**

Because every downstream consumer reads `PortfolioState` and nothing else for account context,
mutating that single object once — at the top of the cycle — is sufficient and leaves the rest of
the pipeline byte-for-byte unchanged. The override is a small pure function plus a thin threading
path from the CLI.

Rejected alternatives:
- *Build a synthetic `PortfolioState` in the CLI and skip `reconcile()`.* Breaks for
  `--ignore-holdings` **without** `--capital`: we'd still need to reconcile for real cash, forcing
  partial-reconcile special-casing. More code, not less.
- *Push the override into the allocator / `_portfolio_value` / `_held_value`.* Scatters the
  "research" concept across allocation, universe-building, research context, and risk. Defeats the
  single-source-of-truth that makes Approach 1 a one-function change.

## 4. Data model & the override function

New frozen value object (run-scoped input, paired with the function below in
`memory/portfolio.py`):

```python
@dataclass(frozen=True)
class PortfolioOverride:
    capital: Decimal | None = None      # override cash AND buying_power to this amount
    ignore_holdings: bool = False       # treat positions as empty (clean slate)

    @property
    def active(self) -> bool:
        return self.capital is not None or self.ignore_holdings
```

One pure function alongside `reconcile`/`enrich_with_quotes`:

```python
def apply_override(state: PortfolioState, override: PortfolioOverride) -> PortfolioState:
    if override.ignore_holdings:
        state = state.model_copy(update={"positions": []})
    if override.capital is not None:
        state = state.model_copy(
            update={"cash": override.capital, "buying_power": override.capital}
        )
    return state
```

Pure, deterministic, no I/O.

## 5. Where it plugs in (data flow)

`run_cycle` gains one optional parameter, `override: PortfolioOverride | None = None`, applied
**between reconcile and enrich** (`core/cycle.py:151-152`):

```python
portfolio = reconcile(deps.broker, deps.settings)
if override is not None:
    portfolio = apply_override(portfolio, override)
portfolio = enrich_with_quotes(portfolio, deps.broker)   # no-op when positions == []
```

The ordering makes every flag combination fall out correctly with no special-casing:

| Flags | positions | cash/bp | `_portfolio_value` result |
|---|---|---|---|
| `--ignore-holdings` only | `[]` | real | real cash (enrich is a no-op → `total_value` stays `None` → cash + 0) |
| `--capital N` only | real | `N` | market value of real holdings + `N` |
| both | `[]` | `N` | exactly `N` |
| neither (override `None` or inactive) | real | real | unchanged from today |

**The override is applied before the `if strategy.buckets:` branch**, so the flat and bucketed
paths both inherit it for free. No code in either path changes.

`account_number` is still the real resolved account (the data layer needs it for the
`fractionable` signal); it is harmless here because execution is blocked (§6).

**Money semantics (confirmed):** `--capital N` overrides **cash** (and buying power). The risk
policy's normal cash-reserve still applies — a `$10,000` what-if deploys ~`$9,500` and reports the
reserve, exactly as a real run would. Capital is *not* a "deploy everything" override.

## 6. CLI surface, lockout & validation

`wizard run` (`cli/app.py` + `cli/run.py`) gains two options:

```
--capital FLOAT        Size to this dollar amount instead of your account's cash.
--ignore-holdings      Treat your account as having no positions (clean slate).
```

Guards in the `run` command, each raising `typer.BadParameter`:

- `--execute` combined with `--capital` or `--ignore-holdings` →
  *"--execute cannot be combined with --capital/--ignore-holdings; research/what-if runs never
  place orders."*
- `--capital` ≤ 0 → *"--capital must be a positive dollar amount."*

`run_strategy` builds the `PortfolioOverride` from the flags and, whenever it is `active`:

- forces `mode = CycleMode.DRY_RUN`, and
- does **not** build the executor or approval gate (passes `None`).

**Execution is therefore blocked at three independent layers:** (1) the CLI guard rejects the flag
combination outright; (2) no executor/approval is constructed; (3) `_execute` already no-ops for
any mode other than `HUMAN_APPROVAL` (`core/cycle.py:82-84`). Belt, suspenders, and a second belt.

`--capital` is declared to Typer as a `float | None` option but converted to `Decimal` via
`Decimal(str(value))` at the boundary, before constructing the override.

## 7. Output & journaling

- **Render banner** (`cli/render.py:render_cycle_result`): when the run's override was active,
  print an unmistakable header line, e.g.
  `🔬 RESEARCH MODE — no orders placed · capital=$10,000.00 · holdings ignored`.
  Only the relevant clauses appear (capital clause only when `--capital` was set; holdings clause
  only when `--ignore-holdings` was set). To render this, `CycleResult` carries the active
  `PortfolioOverride` (or a small derived flag) so `render_cycle_result` can detect it.
- **Journal**: the run is still recorded for audit. `CycleRun.note` tags the mode, e.g.
  `research: capital=10000.00, holdings ignored`. It writes to the normal local journal db, keyed
  by `run_id` — harmless metadata; we do not partition the journal by account in v1.

## 8. Testing

- **`apply_override` (unit, pure):** `--capital` sets `cash` and `buying_power` to the exact
  `Decimal`; `ignore_holdings` empties `positions`; both compose; an inactive override is identity;
  capital is preserved as `Decimal` (no float).
- **`run_cycle` with override:** resulting `PortfolioState` reflects the synthetic values and
  investable derives from `capital`; the executor is **never** invoked even when one is passed
  alongside an active override; both the flat and bucketed paths honor the override.
- **CLI (`cli/run.py`):** each blocked combination (`--execute` + `--capital`, `--execute` +
  `--ignore-holdings`, `--capital <= 0`) raises `BadParameter`; the flags thread into a correct
  `PortfolioOverride`; an active override forces DryRun and builds no executor.
- **Render:** the research banner appears with the right clauses when the override is active, and
  is absent on a normal run.

## 9. Files touched (anticipated)

- `memory/portfolio.py` — `PortfolioOverride` dataclass + `apply_override()`.
- `core/cycle.py` — `run_cycle` gains `override` param; apply between reconcile and enrich; thread
  override (or a derived flag) into `CycleResult` for rendering; `CycleRun.note` tagging.
- `cli/run.py` — accept `capital` / `ignore_holdings`, validate, build override, force DryRun +
  no executor when active.
- `cli/app.py` — add `--capital` / `--ignore-holdings` options to the `run` command.
- `cli/render.py` — research-mode banner.
- `tests/unit/` — `test_portfolio_override.py` (new) plus additions to `test_cli_run.py`,
  `test_render_cycle.py`, and a `run_cycle` override test.
```
