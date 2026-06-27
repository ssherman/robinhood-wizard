# Phase 5 — HumanApproval Order Execution (Design)

- **Date:** 2026-06-27
- **Status:** Approved design (pre-plan)
- **Depends on:** Phases 0–4f (reconcile, risk engine, data layer, the DryRun cycle, LLM
  research/recommend, allocation buckets + allocator, prose→buckets compiler), all merged to main.
- **Scope:** The **first real-money path.** Adds `HumanApproval` execution: `wizard run
  <strategy> --execute` produces the vetted plan exactly as DryRun does, shows a pre-flight
  summary, requires one explicit typed confirmation, then places the approved orders
  (`review_equity_order → place_equity_order`). DryRun stays the default. **Out of scope:**
  Autonomous mode and the automated drawdown kill-switch (deferred to a follow-on phase).

## 1. Goal

Let the agent **place real equity orders, with a human as the final gate on every run.** The
existing pipeline (reconcile → resolve → research/recommend → allocate → risk `vet`) already
produces a deterministically-vetted `TradePlan`; this phase executes the approved intents after
an explicit human confirmation. The deterministic risk engine remains the un-bypassable gate
*before* anything is shown for approval; the human is the gate *before* anything is placed.

## 2. Key findings that shape this phase (from the live order-tool contracts)

`review_equity_order` / `place_equity_order` (Robinhood MCP), confirmed from their schemas:

- **Required:** `account_number` (must be `agentic_allowed=true`; the tool *rejects* non-agentic
  accounts — a structural guardrail), `symbol`, `side`, `type`.
- **`type`:** `market | limit | stop_market | stop_limit`. `limit_price` required for `limit`.
- **`quantity`:** shares. **Decimal (fractional) quantity is allowed only with `type=market`,
  `market_hours=regular_hours`.**
- **`dollar_amount`:** USD notional — **only valid with `type=market`** (server computes shares
  from last trade price).
- **Therefore: a fractional or notional order CANNOT be a limit order** — it must be a market
  order, and fractional/dollar orders execute only during **regular trading hours**.
- **`ref_id`:** an idempotency UUID; Robinhood **dedups by it**. Generate once per logical order,
  re-send on transient retry. → our anti-double-buy key at the gateway.
- **`time_in_force`:** `gfd | gtc` (default `gfd`). **`market_hours`:** `regular_hours` (default).

**Consequence (the central design tension, resolved):** the project's safety model is
*limit orders with a slippage band*, but Robinhood offers no fractional limit order. Whole-share
mode under-deploys badly on a small (~$3k) account (per-bucket budgets split across several
normal-priced names, each floored to whole shares → expensive names floor to 0, remainders
lost; observed ~$230 of $3,000 deployed). Fractional sizing is therefore necessary for a small
account. So this phase **places whole-share intents as LIMIT orders (price-protected) and
fractional/notional intents as MARKET orders** (regular hours), accepting that fractional orders
have no limit-price protection. That protection is replaced for fractional orders by: the
**liquidity floors** the risk engine already enforces (min price / min avg volume / min market
cap → tight spreads), the **dollar-amount cap** (can't overspend), **`review_equity_order`**
surfacing the quote + pre-trade alerts before placing, and the **human confirmation**. The risk
engine's other guards (position size, per-cycle deploy cap, cash reserve, liquidity) still apply
to every intent regardless of order type.

## 3. Decisions (this phase)

| Decision | Choice |
|----------|--------|
| Mode / opt-in | `wizard run <strategy> --execute` runs `CycleMode.HUMAN_APPROVAL`; without `--execute` it stays **DryRun** (default, places nothing). |
| Confirmation | Whole-plan: a pre-flight summary, then **one typed `yes`** (exactly `yes`, not `y`/Enter). **No flag bypasses the confirmation** in this phase (that would be Autonomous). |
| Order mapping | Whole-share (integer `quantity`) → `type=limit` + `limit_price`. Fractional buy (notional `amount`) → `type=market` + `dollar_amount`. Fractional sell (decimal `quantity`) → `type=market` + `quantity`. Whole-share sell → `type=limit` + `quantity` + `limit_price`. `time_in_force=gfd`, `market_hours=regular_hours`. |
| Integrity floor | Per approved intent: `review_equity_order` → `place_equity_order` (with a per-order `ref_id` UUID). |
| Review alert | If `review` returns a blocking alert (insufficient buying power, instrument halt, etc.), **skip that order, journal the skip, continue** the rest (spec §13). |
| Place failure | **Halt the remaining orders, re-reconcile, report** what did/didn't execute — no silent partials (spec §13). |
| Account | The runtime-detected `agentic_allowed` account (`resolve_account_number`); never hardcoded. |
| Interactivity boundary | The cycle stays non-interactive + brain-agnostic; it depends on `OrderExecutor` / `ApprovalGate` Protocols. The interactive gate lives in the CLI; tests inject fakes. |
| Idempotency | reconcile-at-start (buy = budget − current holdings ⇒ re-run never double-buys) + per-order `ref_id` + journal-each-immediately + halt-on-fail. No new persistence. |
| Provider / hours | Robinhood only. Real execution requires **regular trading hours** (fractional/market orders reject otherwise). |

## 4. Architecture & components

### 4.1 Broker: `broker/client.py` (modify)

Add two account-scoped wrappers over the MCP tools (the only new broker methods; mirror the
existing `_call` + payload-coercion style):

- `review_equity_order(account_number, symbol, side, order_type, *, quantity=None, dollar_amount=None, limit_price=None, time_in_force="gfd", market_hours="regular_hours") -> dict`
- `place_equity_order(account_number, symbol, side, order_type, *, quantity=None, dollar_amount=None, limit_price=None, ref_id=None, time_in_force="gfd", market_hours="regular_hours") -> dict`

They forward only the non-None params (the tool's `additionalProperties:false` schema is strict).
Exact response shape is **live-verified during planning** (review returns quote + alerts; place
returns the order; record the shapes in the main spec §18, as prior phases did).

### 4.2 Models: `models/order.py` (new)

- `ReviewResult(ok: bool, estimated_cost: Decimal | None = None, alerts: list[str] = [], raw: dict = {})`
  — `ok` is False when a blocking alert is present (the executor decides from the parsed alerts).
- `OrderResult(symbol: str, side: str, order_type: str, quantity: Decimal | None = None,
  amount: Decimal | None = None, limit_price: Decimal | None = None, order_id: str | None = None,
  status: str, ref_id: str, raw: dict = {})` — `status` ∈ `placed | skipped | failed`.

Plain `Decimal` (these are not LLM-output models).

### 4.3 Execution seam: `execution/base.py` + `execution/robinhood.py` (new)

- `execution/base.py`:
  - `@runtime_checkable OrderExecutor(Protocol)`: `review(intent: TradeIntent, account: str) ->
    ReviewResult`; `place(intent: TradeIntent, account: str, ref_id: str) -> OrderResult`.
  - `@runtime_checkable ApprovalGate(Protocol)`: `confirm(vetted: VettedPlan, portfolio:
    PortfolioState, account: str) -> bool`.
- `execution/robinhood.py`: `RobinhoodOrderExecutor(broker)`:
  - `_order_params(intent)` (pure): maps a `TradeIntent` to `(order_type, kwargs)` per §3 —
    whole-share→limit, fractional(amount or non-integer qty)→market. Unit-tested in isolation.
  - `review`: calls `broker.review_equity_order(...)`, parses → `ReviewResult` (ok=False on a
    blocking alert).
  - `place`: calls `broker.place_equity_order(..., ref_id=ref_id)`, parses → `OrderResult`
    (status `placed`; raises/returns `failed` on error).
  - Imports the broker (typed wrapper) only; no LLM/strands import.

### 4.4 CLI approval gate: `cli/approval.py` (new)

`CliApprovalGate.confirm(...)`: renders the **pre-flight summary** (each approved order:
side / symbol / shares-or-$amount / limit-or-market / estimated cost; the **total estimated
deploy**; the **masked agentic account**) and the explicit warning that real orders will be
placed, then reads a line from stdin and returns `True` only if it equals `yes`. This is the
sole interactive surface; it never places orders itself.

### 4.5 Cycle: `core/cycle.py` (modify)

- `CycleDeps` gains `executor: OrderExecutor | None = None` and `approval: ApprovalGate | None = None`.
- `CycleResult` gains `orders: list[OrderResult] = []` (what was placed/skipped/failed).
- After `vet` (both the flat and bucketed paths converge on a `VettedPlan`), an **execution
  stage** runs only when `mode == CycleMode.HUMAN_APPROVAL` and `deps.executor`/`deps.approval`
  are present and there are approved intents:
  1. `approved = vetted.approved`; if empty, skip (nothing to place).
  2. `if not deps.approval.confirm(vetted, portfolio, account): record a "user declined" note;
     no orders.`
  3. Else, for each approved intent in order: `review` → if `not ok`, append a `skipped`
     `OrderResult` + continue; else `place(intent, account, ref_id=uuid4().hex)` → append the
     `OrderResult`. On a `place` exception: append a `failed` `OrderResult`, **stop the loop**,
     re-reconcile, attach a note.
  4. Journal the orders (record_trades / a `record_orders` method) and set
     `CycleResult.orders`.
- DryRun (default) is unchanged: stops after vet + journal, `orders=[]`. The cycle imports the
  execution Protocols only (brain-agnostic, non-interactive).

### 4.6 Wiring: `cli/run.py` (modify) + `cli/app.py`

- `wizard run` gains a `--execute` flag (default False). When set, build
  `executor=RobinhoodOrderExecutor(broker)` and `approval=CliApprovalGate()`, and pass
  `mode=CycleMode.HUMAN_APPROVAL`; otherwise `mode=CycleMode.DRY_RUN`, no executor/approval.
- The resolved `account_number` (already computed for the data source) is passed through to the
  execution stage.

### 4.7 Journal + render

- Journal: persist each `OrderResult` (reuse the `trades` table via `record_trades`, or a small
  `record_orders`; `source` = the run_id / "agent"). Additive + idempotent.
- Render: an execution summary block — placed / skipped / failed counts, each with order id and
  reason; the existing approved/rejected plan rendering is unchanged.

## 5. Error handling

| Condition | Behavior |
|-----------|----------|
| No `--execute` | DryRun: vet + render + journal; **no orders**, no executor built. |
| `--execute`, user does not type `yes` | Abort execution cleanly; nothing placed; run still journaled with a "declined" note. |
| `--execute`, no approved intents | Nothing to place; render "no approved trades"; no confirmation prompt needed. |
| `review_equity_order` blocking alert | Skip that order (`OrderResult` status `skipped`, alert recorded); continue the rest. |
| `place_equity_order` fails | Record `failed`, **halt remaining**, re-reconcile, report; no silent partials. |
| Reconcile fails (cycle start) | Abort the whole cycle before any execution (existing hard gate). |
| Re-run after a partial/failed run | reconcile sizes buy = budget − current holdings ⇒ no double-buy; `ref_id` dedups at the gateway. |
| Outside regular hours | Market/fractional orders are rejected by the broker → surfaced as `failed`/skip with the broker's reason (run during market hours). |

## 6. Safety

- **DryRun is the default; `--execute` is required; the typed `yes` confirmation is mandatory
  and un-bypassable in this phase.** No autonomous path exists.
- The deterministic risk `vet()` gates every intent **before** it is shown for approval — the
  human only ever sees already-vetted orders.
- Orders go only to the **agentic account** (detected at runtime; the MCP tool itself rejects
  non-agentic accounts).
- Whole-share orders are price-protected **limit** orders; fractional are **market** orders
  guarded by the liquidity floors + `review_equity_order` alerts + the human confirmation +
  the dollar-amount cap (the documented, accepted trade-off).
- **Integrity floor:** reconcile (hard) → vet (hard) → review-before-place → journal-each →
  halt-on-fail. `ref_id` + reconcile prevent double-buys.
- Secrets unchanged: `OPENAI_API_KEY` only in the (unchanged) LLM layer; no secret is logged.

## 7. Testing

- **Offline unit (no network)** via `FakeOrderExecutor` + `FakeApprovalGate`:
  - DryRun (no `--execute`) **never** calls the executor; `orders == []`.
  - `--execute` + approve=True → each approved intent is reviewed then placed (fake records
    calls); `CycleResult.orders` reflects them; journaled.
  - approve=False → **nothing placed**, "declined" note.
  - review-alert (fake returns `ok=False`) → that order `skipped`, the rest continue.
  - place-fail (fake raises) → that order `failed`, **loop halts**, remaining not attempted.
  - `RobinhoodOrderExecutor._order_params`: whole-share→`limit`+limit_price; fractional
    buy→`market`+dollar_amount; fractional sell→`market`+decimal quantity; whole-share
    sell→`limit`. (Pure mapping, exhaustively table-tested.)
  - `ref_id` is generated and passed to `place`.
  - Broker `review_equity_order`/`place_equity_order` forward only non-None params (Scripted MCP).
- **Safety properties:** no order ever placed in DryRun; nothing placed without `confirm()`
  returning True; the executor only ever acts on `vetted.approved` (never rejected intents).
- **Live (opt-in, double-gated `RH_WIZARD_LIVE=1` + token/key):** `review_equity_order` only,
  **never `place`** — assert a review returns a quote/alerts for a known symbol. No real order.
- Both ruff gates clean.

## 8. Out of scope (later phases)

- **Autonomous mode** (no per-run human confirmation) + the **automated drawdown kill-switch**
  + high-water-mark tracking.
- Auto-retry / partial-fill crash recovery beyond halt-and-report; order-status polling after
  placement.
- Per-trade (vs whole-plan) approval granularity.

## 9. Risks to pin during planning

- **Live-verify the `review_equity_order` / `place_equity_order` response shapes** (estimated
  cost + alert fields on review; order id + status on place) and record them in the main spec
  §18 — like the fundamentals/tradability shapes before.
- The blocking-alert classification (which `review` alerts mean "skip"): start conservative —
  treat any alert that indicates the order can't or shouldn't fill (insufficient buying power,
  halt, restricted) as blocking; document the parsed set.
- Keep the interactive gate strictly in `cli/approval.py`; the cycle must remain testable with a
  `FakeApprovalGate` and place nothing in DryRun.
- Decimal discipline end-to-end (quantities/amounts/limit prices as `Decimal`; serialize order
  params as strings the MCP expects).
- Regular-hours dependency: the live first run must be during market hours; document it in the
  README usage.
