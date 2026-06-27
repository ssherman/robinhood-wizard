# Phase 5 — HumanApproval Order Execution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place real equity orders with a human as the final gate — `wizard run <strategy> --execute` produces the vetted plan as DryRun does, shows a pre-flight summary, requires one typed `yes`, then `review_equity_order → place_equity_order` per approved intent. DryRun stays the default.

**Architecture:** A new `OrderExecutor`/`ApprovalGate` seam (Protocols) keeps the cycle non-interactive and brain-agnostic. `RobinhoodOrderExecutor` maps each `TradeIntent` to MCP order params (whole-share → limit; fractional/notional → market) and calls thin new broker wrappers. The cycle gains an execution stage after `vet` that runs only in `HUMAN_APPROVAL` mode: confirm → per-intent review→place with a `ref_id` idempotency key, skip-on-review-alert, halt-on-place-fail, journal each. The CLI provides the interactive gate; tests use fakes and never place a real order.

**Tech Stack:** Python 3.12, uv, pydantic v2, Robinhood MCP (via the typed `BrokerClient`), Typer + rich CLI, SQLite journal, pytest + ruff.

Spec: `docs/superpowers/specs/2026-06-27-robinhood-wizard-phase-5-design.md`.

## Global Constraints

- **DryRun is the default; `--execute` is required to place orders; the typed `yes` confirmation is mandatory and has NO bypass flag this phase.** No autonomous path.
- **No unit/integration test ever places a real order.** Order-flow tests use `FakeOrderExecutor`/`FakeApprovalGate`. The only real-broker test is the opt-in, double-gated live test, and it calls **`review` only, never `place`**.
- **Order mapping:** whole-share (integer `quantity`) → `type=limit` + `limit_price`; fractional buy (notional `amount`) → `type=market` + `dollar_amount`; fractional sell (decimal `quantity`) → `type=market` + `quantity`; whole-share sell → `type=limit` + `quantity` + `limit_price`. `time_in_force="gfd"`, `market_hours="regular_hours"`.
- **Integrity floor:** per approved intent `review_equity_order → place_equity_order` with a per-order `ref_id` UUID. Review blocking-alert → skip + continue. Place failure → halt remaining + report (no silent partials).
- **Agentic account only** — use `portfolio.account_number` (set by reconcile); the MCP tool also rejects non-agentic accounts.
- **Money is `Decimal`, never float;** order params are serialized as strings for the MCP tool.
- The cycle stays brain-agnostic + non-interactive: it depends on `OrderExecutor`/`ApprovalGate` Protocols; the interactive gate lives in `cli/approval.py`.
- Real-broker response shapes for review/place are **unconfirmed** — parse defensively, default conservatively (any review alert ⇒ skip), and live-verify before Monday (record in main spec §18).
- Both ruff gates clean: `uv run ruff check .` and `uv run ruff format --check .`.
- Run a single test with: `uv run pytest tests/unit/<file>::<test> -v`.

## File Structure

**New files**
- `src/rh_wizard/models/order.py` — `ReviewResult`, `OrderResult`.
- `src/rh_wizard/execution/__init__.py`
- `src/rh_wizard/execution/base.py` — `OrderExecutor`, `ApprovalGate` Protocols.
- `src/rh_wizard/execution/robinhood.py` — `RobinhoodOrderExecutor` + `_order_params`.
- `src/rh_wizard/cli/approval.py` — `CliApprovalGate`.
- `tests/unit/test_models_order.py`, `test_order_executor.py`, `test_cli_approval.py`, `test_broker_orders.py`.

**Modified files**
- `src/rh_wizard/broker/client.py` — `review_equity_order`, `place_equity_order`.
- `src/rh_wizard/memory/journal.py` — `record_orders` + `orders` table.
- `src/rh_wizard/core/cycle.py` — `CycleDeps.executor/approval`, `CycleResult.orders`, `_execute` stage in both paths.
- `src/rh_wizard/cli/run.py` + `src/rh_wizard/cli/app.py` — `--execute` flag + wiring.
- `src/rh_wizard/cli/render.py` — execution summary block.
- `README.md`.

---

## Task 1: Order models

**Files:**
- Create: `src/rh_wizard/models/order.py`
- Test: `tests/unit/test_models_order.py`

**Interfaces:**
- Produces:
  - `ReviewResult(ok: bool, estimated_cost: Decimal | None = None, alerts: list[str] = [], raw: dict = {})`
  - `OrderResult(symbol: str, side: str, status: str, order_type: str = "", quantity: Decimal | None = None, amount: Decimal | None = None, limit_price: Decimal | None = None, order_id: str | None = None, ref_id: str = "", raw: dict = {})` — `status` ∈ `"placed" | "skipped" | "failed"`.

- [ ] **Step 1: Write the failing test** — `tests/unit/test_models_order.py`

```python
from decimal import Decimal

from rh_wizard.models.order import OrderResult, ReviewResult


def test_review_result_defaults():
    r = ReviewResult(ok=True)
    assert r.ok is True
    assert r.estimated_cost is None
    assert r.alerts == []
    assert r.raw == {}


def test_review_result_blocking():
    r = ReviewResult(ok=False, alerts=["insufficient buying power"], estimated_cost=Decimal("100"))
    assert r.ok is False
    assert r.alerts == ["insufficient buying power"]


def test_order_result_placed():
    o = OrderResult(
        symbol="AAPL", side="buy", status="placed", order_type="limit",
        quantity=Decimal("3"), limit_price=Decimal("190"), order_id="ord-1", ref_id="ref-1",
    )
    assert o.status == "placed"
    assert o.order_id == "ord-1"
    assert o.quantity == Decimal("3")


def test_order_result_skipped_minimal():
    o = OrderResult(symbol="MU", side="buy", status="skipped", amount=Decimal("180"))
    assert o.status == "skipped"
    assert o.order_type == ""  # default; never placed
    assert o.order_id is None
    assert o.ref_id == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_order.py -v`
Expected: FAIL — `ModuleNotFoundError: rh_wizard.models.order`.

- [ ] **Step 3: Create `src/rh_wizard/models/order.py`**

```python
"""Order execution models (Phase 5). ``ReviewResult`` is what the executor returns from
``review_equity_order`` (estimated cost + pre-trade alerts; ``ok`` is False when a blocking
alert is present). ``OrderResult`` is the outcome of trying to execute one intent —
``status`` is "placed", "skipped" (a blocking review alert), or "failed" (the place call
errored). These are deterministic records, not LLM outputs, so plain ``Decimal``.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class ReviewResult(pydantic.BaseModel):
    ok: bool
    estimated_cost: Decimal | None = None
    alerts: list[str] = []
    raw: dict = {}


class OrderResult(pydantic.BaseModel):
    symbol: str
    side: str
    status: str  # "placed" | "skipped" | "failed"
    order_type: str = ""  # "limit" | "market"; "" when never placed (skipped)
    quantity: Decimal | None = None
    amount: Decimal | None = None
    limit_price: Decimal | None = None
    order_id: str | None = None
    ref_id: str = ""
    raw: dict = {}
```

- [ ] **Step 4: Run the model tests**

Run: `uv run pytest tests/unit/test_models_order.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/models/order.py tests/unit/test_models_order.py
git commit -m "feat: add order execution models (ReviewResult, OrderResult) (Phase 5)"
```

---

## Task 2: Broker review/place wrappers

**Files:**
- Modify: `src/rh_wizard/broker/client.py`
- Test: `tests/unit/test_broker_orders.py`

**Interfaces:**
- Produces (on `BrokerClient`):
  - `review_equity_order(account_number, symbol, side, order_type, *, quantity=None, dollar_amount=None, limit_price=None, time_in_force="gfd", market_hours="regular_hours") -> dict`
  - `place_equity_order(account_number, symbol, side, order_type, *, quantity=None, dollar_amount=None, limit_price=None, ref_id=None, time_in_force="gfd", market_hours="regular_hours") -> dict`
  - Both forward only non-None params and return the coerced payload dict (`self._call`).

- [ ] **Step 1: Write the failing test** — `tests/unit/test_broker_orders.py`

```python
# tests/unit/test_broker_orders.py
from rh_wizard.broker.client import BrokerClient


class ScriptedMCPClient:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return []

    def call_tool_sync(self, *, tool_use_id, name, arguments=None):
        assert self.entered
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_review_equity_order_forwards_only_non_none():
    fake = ScriptedMCPClient([{"data": {"quote": {"last_trade_price": "190"}}}])
    with BrokerClient(fake) as broker:
        out = broker.review_equity_order("ACC1", "AAPL", "buy", "limit", quantity="3", limit_price="190")
    assert out  # payload returned
    name, args = fake.calls[0]
    assert name == "review_equity_order"
    assert args == {
        "account_number": "ACC1", "symbol": "AAPL", "side": "buy", "type": "limit",
        "quantity": "3", "limit_price": "190",
        "time_in_force": "gfd", "market_hours": "regular_hours",
    }
    assert "dollar_amount" not in args  # None params dropped


def test_place_equity_order_market_notional_with_ref_id():
    fake = ScriptedMCPClient([{"data": {"id": "ord-1"}}])
    with BrokerClient(fake) as broker:
        broker.place_equity_order("ACC1", "MU", "buy", "market", dollar_amount="180.00", ref_id="r-1")
    name, args = fake.calls[0]
    assert name == "place_equity_order"
    assert args["type"] == "market"
    assert args["dollar_amount"] == "180.00"
    assert args["ref_id"] == "r-1"
    assert "quantity" not in args and "limit_price" not in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_broker_orders.py -v`
Expected: FAIL — `AttributeError: 'BrokerClient' object has no attribute 'review_equity_order'`.

- [ ] **Step 3: Add the wrappers** — `src/rh_wizard/broker/client.py`

Add these two methods to `BrokerClient` (after `get_equity_tradability`):

```python
    def review_equity_order(
        self,
        account_number: str,
        symbol: str,
        side: str,
        order_type: str,
        *,
        quantity: str | None = None,
        dollar_amount: str | None = None,
        limit_price: str | None = None,
        time_in_force: str = "gfd",
        market_hours: str = "regular_hours",
    ) -> dict:
        """Simulate an equity order (quote + pre-trade alerts) without placing it. Forwards
        only the non-None sizing params (the tool's schema is strict). Requires an
        agentic_allowed account; the tool rejects non-agentic accounts."""
        return self._call(
            "review_equity_order",
            **_order_args(
                account_number, symbol, side, order_type, quantity, dollar_amount,
                limit_price, time_in_force, market_hours,
            ),
        )

    def place_equity_order(
        self,
        account_number: str,
        symbol: str,
        side: str,
        order_type: str,
        *,
        quantity: str | None = None,
        dollar_amount: str | None = None,
        limit_price: str | None = None,
        ref_id: str | None = None,
        time_in_force: str = "gfd",
        market_hours: str = "regular_hours",
    ) -> dict:
        """Place a REAL equity order. Forwards only non-None params; ``ref_id`` is the
        idempotency key (Robinhood dedups by it). Requires an agentic_allowed account."""
        args = _order_args(
            account_number, symbol, side, order_type, quantity, dollar_amount,
            limit_price, time_in_force, market_hours,
        )
        if ref_id is not None:
            args["ref_id"] = ref_id
        return self._call("place_equity_order", **args)
```

Add this module-level helper (near `_chunked` / the other helpers):

```python
def _order_args(
    account_number: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | None,
    dollar_amount: str | None,
    limit_price: str | None,
    time_in_force: str,
    market_hours: str,
) -> dict:
    """Build the MCP order arguments, dropping None sizing params (strict schema)."""
    args: dict = {
        "account_number": account_number,
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
        "market_hours": market_hours,
    }
    if quantity is not None:
        args["quantity"] = quantity
    if dollar_amount is not None:
        args["dollar_amount"] = dollar_amount
    if limit_price is not None:
        args["limit_price"] = limit_price
    return args
```

- [ ] **Step 4: Run the broker tests**

Run: `uv run pytest tests/unit/test_broker_orders.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/broker/client.py tests/unit/test_broker_orders.py
git commit -m "feat: add review_equity_order/place_equity_order broker wrappers (Phase 5)"
```

---

## Task 3: Execution seam + RobinhoodOrderExecutor

**Files:**
- Create: `src/rh_wizard/execution/__init__.py`, `src/rh_wizard/execution/base.py`, `src/rh_wizard/execution/robinhood.py`
- Test: `tests/unit/test_order_executor.py`

**Interfaces:**
- Consumes: `TradeIntent` (`models/plan.py`); `ReviewResult`/`OrderResult` (Task 1); broker wrappers (Task 2); `VettedPlan`, `PortfolioState` (for the `ApprovalGate` Protocol).
- Produces:
  - `OrderExecutor` Protocol: `review(intent, account) -> ReviewResult`, `place(intent, account, ref_id) -> OrderResult`.
  - `ApprovalGate` Protocol: `confirm(vetted, portfolio, account) -> bool`.
  - `RobinhoodOrderExecutor(broker)` implementing `OrderExecutor`; module-level `_order_params(intent) -> tuple[str, dict]`.

- [ ] **Step 1: Write the failing test** — `tests/unit/test_order_executor.py`

```python
from decimal import Decimal

from rh_wizard.execution.base import OrderExecutor
from rh_wizard.execution.robinhood import RobinhoodOrderExecutor, _order_params
from rh_wizard.models.plan import TradeIntent


def test_order_params_whole_share_is_limit():
    intent = TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190")
    order_type, params = _order_params(intent)
    assert order_type == "limit"
    assert params == {"quantity": "3", "limit_price": "190"}


def test_order_params_fractional_buy_is_market_notional():
    intent = TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99")
    order_type, params = _order_params(intent)
    assert order_type == "market"
    assert params == {"dollar_amount": "180.00"}  # no limit price on a market order


def test_order_params_fractional_sell_is_market_quantity():
    intent = TradeIntent(side="sell", symbol="NVDA", quantity="1.5", limit_price="100")
    order_type, params = _order_params(intent)
    assert order_type == "market"
    assert params == {"quantity": "1.5"}


def test_order_params_whole_sell_is_limit():
    intent = TradeIntent(side="sell", symbol="NVDA", quantity="2", limit_price="100")
    order_type, params = _order_params(intent)
    assert order_type == "limit"
    assert params == {"quantity": "2", "limit_price": "100"}


class FakeBroker:
    def __init__(self):
        self.placed = []

    def review_equity_order(self, account_number, symbol, side, order_type, **kw):
        return {"data": {"estimated_cost": "570.00", "alerts": []}}

    def place_equity_order(self, account_number, symbol, side, order_type, *, ref_id=None, **kw):
        self.placed.append((symbol, order_type, ref_id, kw))
        return {"data": {"id": "ord-123", "state": "confirmed"}}


def test_review_ok_when_no_alerts():
    ex = RobinhoodOrderExecutor(FakeBroker())
    rv = ex.review(TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1")
    assert rv.ok is True
    assert rv.estimated_cost == Decimal("570.00")


def test_review_blocks_on_alerts():
    class AlertBroker(FakeBroker):
        def review_equity_order(self, *a, **k):
            return {"data": {"alerts": ["insufficient buying power"]}}

    ex = RobinhoodOrderExecutor(AlertBroker())
    rv = ex.review(TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1")
    assert rv.ok is False
    assert "insufficient buying power" in rv.alerts


def test_place_returns_placed_orderresult_with_ref_id():
    broker = FakeBroker()
    ex = RobinhoodOrderExecutor(broker)
    intent = TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99")
    out = ex.place(intent, "ACC1", "ref-1")
    assert out.status == "placed"
    assert out.order_id == "ord-123"
    assert out.ref_id == "ref-1"
    assert broker.placed[0][2] == "ref-1"  # ref_id forwarded


def test_place_failure_returns_failed_orderresult():
    class BoomBroker(FakeBroker):
        def place_equity_order(self, *a, **k):
            raise RuntimeError("gateway 500")

    ex = RobinhoodOrderExecutor(BoomBroker())
    out = ex.place(TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1", "r")
    assert out.status == "failed"
    assert "gateway 500" in str(out.raw)


def test_satisfies_executor_protocol():
    assert isinstance(RobinhoodOrderExecutor(FakeBroker()), OrderExecutor)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_order_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: rh_wizard.execution`.

- [ ] **Step 3a: Create `src/rh_wizard/execution/__init__.py`** (empty)

```python
```

- [ ] **Step 3b: Create `src/rh_wizard/execution/base.py`**

```python
"""The order-execution seams (Phase 5). ``OrderExecutor`` reviews then places a single
``TradeIntent`` (the broker boundary). ``ApprovalGate`` asks the human whether to place the
whole vetted plan. The cycle depends on these Protocols so it stays non-interactive and
testable without a broker or a terminal.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.order import OrderResult, ReviewResult
from rh_wizard.models.plan import TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState


@runtime_checkable
class OrderExecutor(Protocol):
    def review(self, intent: TradeIntent, account: str) -> ReviewResult: ...
    def place(self, intent: TradeIntent, account: str, ref_id: str) -> OrderResult: ...


@runtime_checkable
class ApprovalGate(Protocol):
    def confirm(self, vetted: VettedPlan, portfolio: PortfolioState, account: str) -> bool: ...
```

- [ ] **Step 3c: Create `src/rh_wizard/execution/robinhood.py`**

```python
"""Robinhood-backed order executor (Phase 5). Maps a vetted ``TradeIntent`` to MCP order
params and calls the typed broker wrappers. Whole-share intents become price-protected LIMIT
orders; fractional/notional intents become MARKET orders (Robinhood has no fractional limit
order). Imports the typed broker only — no LLM/strands. Real response shapes are parsed
defensively and live-verified (spec §18).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rh_wizard.models.order import OrderResult, ReviewResult
from rh_wizard.models.plan import TradeIntent


def _order_params(intent: TradeIntent) -> tuple[str, dict]:
    """(order_type, sizing-params) for an intent. Fractional/notional → market; whole → limit."""
    if intent.amount is not None:  # fractional buy: notional market order
        return "market", {"dollar_amount": str(intent.amount)}
    if intent.quantity is not None and intent.quantity != intent.quantity.to_integral_value():
        return "market", {"quantity": str(intent.quantity)}  # fractional sell: market
    if intent.quantity is not None and intent.limit_price is not None:
        return "limit", {"quantity": str(intent.quantity), "limit_price": str(intent.limit_price)}
    raise ValueError(f"cannot size order for {intent.symbol}: need amount, or quantity+limit_price")


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _unwrap(raw: dict) -> dict:
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def _parse_alerts(raw: dict) -> list[str]:
    alerts = _unwrap(raw).get("alerts")
    if not alerts:
        return []
    return [a if isinstance(a, str) else str(a) for a in alerts]


def _parse_order_id(raw: dict) -> str | None:
    d = _unwrap(raw)
    val = d.get("id") or d.get("order_id")
    return str(val) if val else None


class RobinhoodOrderExecutor:
    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def review(self, intent: TradeIntent, account: str) -> ReviewResult:
        order_type, params = _order_params(intent)
        try:
            raw = self._broker.review_equity_order(
                account, intent.symbol, intent.side, order_type, **params
            )
        except Exception as exc:  # a review that errors is a blocking condition → skip
            return ReviewResult(ok=False, alerts=[f"review failed: {exc}"], raw={})
        alerts = _parse_alerts(raw)
        cost = _to_decimal(_unwrap(raw).get("estimated_cost"))
        return ReviewResult(ok=not alerts, estimated_cost=cost, alerts=alerts, raw=raw)

    def place(self, intent: TradeIntent, account: str, ref_id: str) -> OrderResult:
        order_type, params = _order_params(intent)
        try:
            raw = self._broker.place_equity_order(
                account, intent.symbol, intent.side, order_type, ref_id=ref_id, **params
            )
        except Exception as exc:  # never raise into the cycle; return a failed result
            return OrderResult(
                symbol=intent.symbol, side=intent.side, status="failed", order_type=order_type,
                quantity=intent.quantity, amount=intent.amount, limit_price=intent.limit_price,
                ref_id=ref_id, raw={"error": str(exc)},
            )
        return OrderResult(
            symbol=intent.symbol, side=intent.side, status="placed", order_type=order_type,
            quantity=intent.quantity, amount=intent.amount, limit_price=intent.limit_price,
            order_id=_parse_order_id(raw), ref_id=ref_id, raw=raw,
        )
```

- [ ] **Step 4: Run the executor tests**

Run: `uv run pytest tests/unit/test_order_executor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/execution/__init__.py src/rh_wizard/execution/base.py src/rh_wizard/execution/robinhood.py tests/unit/test_order_executor.py
git commit -m "feat: add OrderExecutor seam + RobinhoodOrderExecutor (Phase 5)"
```

---

## Task 4: CLI approval gate

**Files:**
- Create: `src/rh_wizard/cli/approval.py`
- Test: `tests/unit/test_cli_approval.py`

**Interfaces:**
- Consumes: `VettedPlan`, `PortfolioState`; `_intent_amount` (`cli/render.py`); `mask_account` (`masking.py`); `fmt_money`/`fmt_num` (`cli/render.py`).
- Produces: `CliApprovalGate` implementing `ApprovalGate.confirm(vetted, portfolio, account) -> bool` — prints a pre-flight summary and returns True only if stdin reads exactly `yes`.

- [ ] **Step 1: Write the failing test** — `tests/unit/test_cli_approval.py`

```python
import io
from decimal import Decimal

from rh_wizard.cli.approval import CliApprovalGate
from rh_wizard.execution.base import ApprovalGate
from rh_wizard.models.plan import TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState


def _vetted():
    return VettedPlan(
        approved=[
            TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"),
            TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99"),
        ]
    )


def _portfolio():
    return PortfolioState(account_number="ACC1234567890", positions=[], cash="3000", buying_power="3000")


def test_confirm_true_only_on_exact_yes(capsys):
    gate = CliApprovalGate(stdin=io.StringIO("yes\n"))
    assert gate.confirm(_vetted(), _portfolio(), "ACC1234567890") is True
    out = capsys.readouterr().out
    assert "AAPL" in out and "MU" in out          # orders listed
    assert "7890" in out and "ACC1234567890" not in out  # account masked
    assert "$570.00" in out or "570" in out        # est. cost shown (3 * 190)


def test_confirm_false_on_anything_else(capsys):
    assert CliApprovalGate(stdin=io.StringIO("y\n")).confirm(_vetted(), _portfolio(), "ACC1234567890") is False
    assert CliApprovalGate(stdin=io.StringIO("\n")).confirm(_vetted(), _portfolio(), "ACC1234567890") is False
    assert CliApprovalGate(stdin=io.StringIO("no\n")).confirm(_vetted(), _portfolio(), "ACC1234567890") is False


def test_satisfies_approval_protocol():
    assert isinstance(CliApprovalGate(), ApprovalGate)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_approval.py -v`
Expected: FAIL — `ModuleNotFoundError: rh_wizard.cli.approval`.

- [ ] **Step 3: Create `src/rh_wizard/cli/approval.py`**

```python
"""Interactive whole-plan approval gate (Phase 5). The ONLY interactive surface in the
execution path: it renders a pre-flight summary of the vetted plan (orders, total estimated
deploy, masked agentic account) and requires the operator to type exactly ``yes`` before any
real order is placed. It never places orders itself.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from typing import TextIO

from rh_wizard.cli.render import _intent_amount, fmt_money, fmt_num
from rh_wizard.masking import mask_account
from rh_wizard.models.plan import VettedPlan
from rh_wizard.models.portfolio import PortfolioState


class CliApprovalGate:
    def __init__(self, stdin: TextIO | None = None) -> None:
        self._stdin = stdin if stdin is not None else sys.stdin

    def confirm(self, vetted: VettedPlan, portfolio: PortfolioState, account: str) -> bool:
        total = sum((_intent_amount(i) or Decimal("0")) for i in vetted.approved)
        print(
            f"\nAbout to place {len(vetted.approved)} REAL order(s) "
            f"(~{fmt_money(total)}) in account {mask_account(account)}:"
        )
        for i in vetted.approved:
            qty = fmt_num(i.quantity) if i.quantity is not None else "-"
            kind = "limit" if i.limit_price is not None and i.amount is None else "market"
            print(
                f"  {i.side} {i.symbol}  qty={qty}  {kind} {fmt_money(i.limit_price)}  "
                f"amount={fmt_money(_intent_amount(i))}"
            )
        print("Type 'yes' to place these orders (anything else cancels): ", end="")
        answer = self._stdin.readline().strip()
        return answer == "yes"
```

- [ ] **Step 4: Run the approval tests**

Run: `uv run pytest tests/unit/test_cli_approval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/cli/approval.py tests/unit/test_cli_approval.py
git commit -m "feat: add CliApprovalGate (typed-yes whole-plan confirmation) (Phase 5)"
```

---

## Task 5: Journal — record_orders

**Files:**
- Modify: `src/rh_wizard/memory/journal.py`
- Test: `tests/unit/test_journal.py`

**Interfaces:**
- Consumes: `OrderResult` (Task 1).
- Produces: `SqliteJournal.record_orders(run_id, orders: list[OrderResult]) -> None`; reader `orders(run_id) -> list[dict]`. New idempotent `orders` table.

- [ ] **Step 1: Write the failing test** — append to `tests/unit/test_journal.py`

```python
def test_record_orders_roundtrips():
    from decimal import Decimal

    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.order import OrderResult

    orders = [
        OrderResult(symbol="AAPL", side="buy", status="placed", order_type="limit",
                    quantity=Decimal("3"), limit_price=Decimal("190"), order_id="ord-1", ref_id="r-1"),
        OrderResult(symbol="MU", side="buy", status="skipped", amount=Decimal("180")),
    ]
    with SqliteJournal(":memory:") as j:
        j.record_orders("run1", orders)
        rows = j.orders("run1")
        assert [r["symbol"] for r in rows] == ["AAPL", "MU"]
        assert rows[0]["status"] == "placed" and rows[0]["order_id"] == "ord-1"
        assert rows[0]["ref_id"] == "r-1" and rows[0]["quantity"] == "3"
        assert rows[1]["status"] == "skipped" and rows[1]["amount"] == "180"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_journal.py::test_record_orders_roundtrips -v`
Expected: FAIL — `AttributeError: 'SqliteJournal' object has no attribute 'record_orders'`.

- [ ] **Step 3a: Add the table** — append to `_SCHEMA` in `src/rh_wizard/memory/journal.py`

```python
CREATE TABLE IF NOT EXISTS orders (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    status      TEXT NOT NULL,
    order_type  TEXT,
    quantity    TEXT,
    amount      TEXT,
    limit_price TEXT,
    order_id    TEXT,
    ref_id      TEXT,
    PRIMARY KEY (run_id, seq)
);
```

- [ ] **Step 3b: Add the import** — top of `journal.py`

```python
from rh_wizard.models.order import OrderResult
```

- [ ] **Step 3c: Add the methods** — `SqliteJournal` (after `recommendation_sources`)

```python
    def record_orders(self, run_id: str, orders: list[OrderResult]) -> None:
        self._conn.execute("DELETE FROM orders WHERE run_id = ?", (run_id,))
        rows = [
            {
                "run_id": run_id, "seq": i, "symbol": o.symbol, "side": o.side,
                "status": o.status, "order_type": o.order_type,
                "quantity": None if o.quantity is None else str(o.quantity),
                "amount": None if o.amount is None else str(o.amount),
                "limit_price": None if o.limit_price is None else str(o.limit_price),
                "order_id": o.order_id, "ref_id": o.ref_id,
            }
            for i, o in enumerate(orders)
        ]
        if rows:
            self._conn.executemany(
                "INSERT INTO orders (run_id, seq, symbol, side, status, order_type, quantity, "
                "amount, limit_price, order_id, ref_id) VALUES (:run_id, :seq, :symbol, :side, "
                ":status, :order_type, :quantity, :amount, :limit_price, :order_id, :ref_id);",
                rows,
            )
        self._conn.commit()

    def orders(self, run_id: str) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM orders WHERE run_id = ? ORDER BY seq", (run_id,))
        return [dict(row) for row in cur.fetchall()]
```

- [ ] **Step 4: Run the journal tests**

Run: `uv run pytest tests/unit/test_journal.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/memory/journal.py tests/unit/test_journal.py
git commit -m "feat: journal placed/skipped/failed orders (Phase 5)"
```

---

## Task 6: Cycle execution stage

**Files:**
- Modify: `src/rh_wizard/core/cycle.py`
- Test: `tests/unit/test_cycle.py`

**Interfaces:**
- Consumes: `OrderExecutor`/`ApprovalGate` (Task 3); `OrderResult` (Task 1); `record_orders` (Task 5); `CycleMode.HUMAN_APPROVAL`.
- Produces: `CycleDeps.executor: OrderExecutor | None = None`, `CycleDeps.approval: ApprovalGate | None = None`; `CycleResult.orders: list[OrderResult] = []`; a module-level `_execute(deps, run, portfolio, vetted) -> list[OrderResult]` called in both the flat and bucketed success paths (account = `portfolio.account_number`).

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_cycle.py`

```python
def _fake_intent(symbol="AAPL"):
    from rh_wizard.models.plan import TradeIntent

    return TradeIntent(side="buy", symbol=symbol, quantity="1", limit_price="100")


class _YesGate:
    def confirm(self, vetted, portfolio, account):
        self.account = account
        return True


class _NoGate:
    def confirm(self, vetted, portfolio, account):
        return False


class _RecordingExecutor:
    def __init__(self, review_ok=True, place_fails=False):
        self._review_ok = review_ok
        self._place_fails = place_fails
        self.reviewed = []
        self.placed = []

    def review(self, intent, account):
        from rh_wizard.models.order import ReviewResult

        self.reviewed.append(intent.symbol)
        return ReviewResult(ok=self._review_ok, alerts=[] if self._review_ok else ["blocked"])

    def place(self, intent, account, ref_id):
        from rh_wizard.models.order import OrderResult

        self.placed.append((intent.symbol, ref_id))
        status = "failed" if self._place_fails else "placed"
        return OrderResult(symbol=intent.symbol, side=intent.side, status=status,
                           order_type="limit", quantity=intent.quantity, ref_id=ref_id,
                           order_id=None if self._place_fails else "ord")


def _human_approval():
    from rh_wizard.models.cycle import CycleMode

    return CycleMode.HUMAN_APPROVAL


def test_dryrun_never_executes():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps)  # default DryRun
        assert result.orders == []
        assert ex.placed == []  # executor never called in DryRun


def test_human_approval_places_approved_orders():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.run.status == "completed"
        assert [o.symbol for o in result.orders] == ["AAPL"]
        assert result.orders[0].status == "placed"
        assert ex.placed and ex.placed[0][1]  # a ref_id was passed
        assert deps.approval.account == "ACC1"  # the reconciled agentic account
        assert journal.orders(result.run.run_id)[0]["status"] == "placed"


def test_human_approval_declined_places_nothing():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _NoGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.orders == []
        assert ex.placed == []


def test_review_alert_skips_order():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor(review_ok=False)
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.orders[0].status == "skipped"
        assert ex.placed == []  # never placed after a blocking review


def test_place_failure_halts_remaining():
    # Two approved intents; the first place fails -> the second is never attempted.
    strategy = Strategy(id="m", name="M", universe=["AAPL", "MSFT"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor(place_fails=True)
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        statuses = [o.status for o in result.orders]
        assert statuses == ["failed"]      # halted after the first failure
        assert len(ex.placed) == 1         # the second was not attempted
```

Note: the stub `StubPlanner`/`StubResearcher` used by `_deps` propose 1-share probe buys, so the flat universe `["AAPL"]` yields one approved AAPL intent (and `["AAPL","MSFT"]` yields two) — matching the assertions above.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cycle.py -k "execut or approval or review_alert or place_failure or dryrun" -v`
Expected: FAIL — `CycleDeps` has no `executor`/`approval`; `CycleResult` has no `orders`.

- [ ] **Step 3a: Imports + dataclass fields** — `src/rh_wizard/core/cycle.py`

Add imports:

```python
from rh_wizard.execution.base import ApprovalGate, OrderExecutor
from rh_wizard.models.order import OrderResult
```

Add to `CycleDeps`:

```python
    executor: OrderExecutor | None = None
    approval: ApprovalGate | None = None
```

Add to `CycleResult`:

```python
    orders: list[OrderResult] = field(default_factory=list)
```

(Add `from dataclasses import dataclass, field` — update the existing dataclass import.)

- [ ] **Step 3b: Add the `_execute` helper** — `core/cycle.py` (after `_now`/`_norm`)

```python
def _execute(
    deps: CycleDeps, run: CycleRun, portfolio: PortfolioState, vetted: VettedPlan
) -> list[OrderResult]:
    """HumanApproval execution: confirm once, then review→place each approved intent.
    No-op unless mode is HUMAN_APPROVAL with an executor + approval gate + approved intents.
    review blocking-alert → skip+continue; place failure → halt remaining (spec §13)."""
    if run.mode != CycleMode.HUMAN_APPROVAL.value:
        return []
    if deps.executor is None or deps.approval is None or not vetted.approved:
        return []
    account = portfolio.account_number
    if not deps.approval.confirm(vetted, portfolio, account):
        return []  # user declined; nothing placed
    orders: list[OrderResult] = []
    for intent in vetted.approved:
        review = deps.executor.review(intent, account)
        if not review.ok:
            orders.append(
                OrderResult(
                    symbol=intent.symbol, side=intent.side, status="skipped",
                    quantity=intent.quantity, amount=intent.amount, limit_price=intent.limit_price,
                    raw={"alerts": review.alerts},
                )
            )
            continue
        result = deps.executor.place(intent, account, uuid.uuid4().hex)
        orders.append(result)
        if result.status == "failed":
            break  # halt remaining; no silent partials
    return orders
```

- [ ] **Step 3c: Wire it into the FLAT success path** — replace the flat success/return block (the `# Stage 9: DryRun ...` section through the final `return CycleResult(...)`):

```python
    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)
    deps.journal.record_research(run.run_id, report)
    if discovery is not None:
        deps.journal.record_discovery(run.run_id, discovery)

    orders = _execute(deps, run, portfolio, vetted)
    deps.journal.record_orders(run.run_id, orders)

    return CycleResult(
        run=run, portfolio=portfolio, market=market, report=report, plan=plan,
        vetted=vetted, discovery=discovery, orders=orders,
    )
```

- [ ] **Step 3d: Wire it into the BUCKETED success path** — in `_run_bucketed`, replace its success/return block (from `run = run.model_copy(update={"status": "completed", ...})` to the end):

```python
    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)
    deps.journal.record_allocation(run.run_id, allocation, recommendation)

    orders = _execute(deps, run, portfolio, vetted)
    deps.journal.record_orders(run.run_id, orders)

    return CycleResult(
        run=run, portfolio=portfolio, market=market, plan=plan, vetted=vetted,
        recommendation=recommendation, allocation=allocation, orders=orders,
    )
```

- [ ] **Step 4: Run the cycle tests**

Run: `uv run pytest tests/unit/test_cycle.py -v`
Expected: PASS (new execution tests + all existing DryRun tests).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/core/cycle.py tests/unit/test_cycle.py
git commit -m "feat: add HumanApproval execution stage to the cycle (Phase 5)"
```

---

## Task 7: CLI wiring (`--execute`)

**Files:**
- Modify: `src/rh_wizard/cli/app.py`, `src/rh_wizard/cli/run.py`
- Test: `tests/unit/test_cli_run.py`

**Interfaces:**
- Consumes: `RobinhoodOrderExecutor` (Task 3), `CliApprovalGate` (Task 4), the cycle execution stage (Task 6).
- Produces: `wizard run <strategy> --execute` runs `CycleMode.HUMAN_APPROVAL` with a real executor + interactive gate; without `--execute` it stays DryRun. `run_strategy(strategy_id, execute: bool = False)`.

- [ ] **Step 1: Write the failing test** — append to `tests/unit/test_cli_run.py`

```python
def test_run_execute_flag_runs_human_approval(monkeypatch, tmp_path):
    from rh_wizard.cli import run as run_module
    from rh_wizard.models.order import OrderResult, ReviewResult

    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)  # flat demo strategy, web_research: false

    placed = []

    class FakeExecutor:
        def review(self, intent, account):
            return ReviewResult(ok=True)

        def place(self, intent, account, ref_id):
            placed.append(intent.symbol)
            return OrderResult(symbol=intent.symbol, side=intent.side, status="placed",
                               order_type="limit", quantity=intent.quantity, ref_id=ref_id, order_id="o")

    class YesGate:
        def confirm(self, vetted, portfolio, account):
            return True

    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    monkeypatch.setattr(run_module, "_build_executor", lambda broker: FakeExecutor())
    monkeypatch.setattr(run_module, "_build_approval", lambda: YesGate())

    result = runner.invoke(app, ["run", "demo", "--execute"])
    assert result.exit_code == 0, result.output
    assert placed == ["AAPL"]  # real-execution path ran via the fakes


def test_run_without_execute_places_nothing(monkeypatch, tmp_path):
    from rh_wizard.cli import run as run_module

    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)

    class BoomExecutor:
        def review(self, intent, account):
            raise AssertionError("executor must not run in DryRun")

        def place(self, intent, account, ref_id):
            raise AssertionError("executor must not run in DryRun")

    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    monkeypatch.setattr(run_module, "_build_executor", lambda broker: BoomExecutor())
    result = runner.invoke(app, ["run", "demo"])  # no --execute
    assert result.exit_code == 0
    assert "DryRun" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_run.py -k execute -v`
Expected: FAIL — `run` has no `--execute` option / `_build_executor` missing.

- [ ] **Step 3a: Add the flag** — `src/rh_wizard/cli/app.py`, the `run` command

```python
@app.command()
def run(
    strategy_id: str = typer.Argument(..., help="Strategy id (yaml filename stem)."),  # noqa: B008
    execute: bool = typer.Option(  # noqa: B008
        False, "--execute", help="Place REAL orders after a typed confirmation (HumanApproval). "
        "Default is DryRun (no orders).",
    ),
) -> None:
    run_strategy(strategy_id, execute=execute)
```

- [ ] **Step 3b: Add the lazy builders + wire** — `src/rh_wizard/cli/run.py`

Add builders (next to `_build_recommender`):

```python
def _build_executor(broker):
    """Build the real order executor (patched in tests)."""
    from rh_wizard.execution.robinhood import RobinhoodOrderExecutor

    return RobinhoodOrderExecutor(broker)


def _build_approval():
    """Build the interactive approval gate (patched in tests)."""
    from rh_wizard.cli.approval import CliApprovalGate

    return CliApprovalGate()
```

Change `run_strategy` to accept `execute` and wire the deps + mode. Replace the signature and the `deps = CycleDeps(...)` / `run_cycle(...)` tail:

```python
def run_strategy(strategy_id: str, execute: bool = False) -> None:
    paths.ensure_home()
    settings = load_settings()
    registry = StrategyRegistry(paths.strategies_dir())
    try:
        strategy = registry.load(strategy_id)
    except StrategyNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    broker = auth._build_broker(settings)
    with broker, SqliteJournal(paths.db_path()) as journal:
        account_number = resolve_account_number(broker, settings)
        resolver = SignalResolver([RobinhoodDataSource(broker, account_number)])
        llm = _build_llm(settings)
        researcher = (
            _build_web_researcher(settings) if strategy.web_research else LlmResearcher(llm)
        )
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=researcher,
            planner=LlmPlanner(llm),
            journal=journal,
            discoverer=(
                _build_discoverer(settings)
                if strategy.discover or any(b.discover for b in strategy.buckets)
                else None
            ),
            recommender=_build_recommender(settings) if strategy.buckets else None,
            executor=_build_executor(broker) if execute else None,
            approval=_build_approval() if execute else None,
        )
        mode = CycleMode.HUMAN_APPROVAL if execute else CycleMode.DRY_RUN
        result = run_cycle(strategy, deps, mode)
    typer.echo(render_cycle_result(result))
```

- [ ] **Step 4: Run the CLI tests**

Run: `uv run pytest tests/unit/test_cli_run.py -v`
Expected: PASS (new execute tests + existing DryRun/flat/bucketed run tests).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/cli/app.py src/rh_wizard/cli/run.py tests/unit/test_cli_run.py
git commit -m "feat: wire wizard run --execute (HumanApproval) (Phase 5)"
```

---

## Task 8: Render execution summary

**Files:**
- Modify: `src/rh_wizard/cli/render.py`
- Test: `tests/unit/test_render_cycle.py`

**Interfaces:**
- Consumes: `CycleResult.orders` (Task 6).
- Produces: `render_cycle_result` appends an "Execution" block when `result.orders` is non-empty — placed/skipped/failed per order with order id / reason.

- [ ] **Step 1: Write the failing test** — append to `tests/unit/test_render_cycle.py`

```python
def test_render_shows_execution_summary():
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.core.cycle import CycleResult
    from rh_wizard.models.order import OrderResult
    from rh_wizard.models.plan import VettedPlan

    result = CycleResult(
        run=_run(),
        vetted=VettedPlan(),
        orders=[
            OrderResult(symbol="AAPL", side="buy", status="placed", order_type="limit",
                        quantity=Decimal("3"), order_id="ord-1"),
            OrderResult(symbol="MU", side="buy", status="skipped", amount=Decimal("180"),
                        raw={"alerts": ["insufficient buying power"]}),
        ],
    )
    out = render_cycle_result(result)
    assert "Execution" in out
    assert "AAPL" in out and "placed" in out and "ord-1" in out
    assert "MU" in out and "skipped" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render_cycle.py::test_render_shows_execution_summary -v`
Expected: FAIL — no "Execution" block.

- [ ] **Step 3: Add the block** — in `render_cycle_result` (`src/rh_wizard/cli/render.py`), after the approved/rejected plan rendering and before the final `"DryRun — no orders placed."` footer line, insert:

```python
    orders = getattr(result, "orders", None)
    if orders:
        table = Table(title="Execution")
        table.add_column("Side")
        table.add_column("Symbol")
        table.add_column("Status")
        table.add_column("Order id")
        for o in orders:
            note = o.order_id or (", ".join(o.raw.get("alerts", [])) if isinstance(o.raw, dict) else "")
            table.add_row(o.side, o.symbol, o.status, note or "-")
        lines.append(render_to_str(table).rstrip("\n"))
```

And change the footer so it reflects execution — replace the final
`lines.append("DryRun — no orders placed.")` with:

```python
    if getattr(result, "orders", None):
        placed = sum(1 for o in result.orders if o.status == "placed")
        lines.append(f"Executed: {placed} placed, {len(result.orders) - placed} not placed.")
    else:
        lines.append("DryRun — no orders placed.")
```

- [ ] **Step 4: Run the render tests**

Run: `uv run pytest tests/unit/test_render_cycle.py tests/unit/test_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/cli/render.py tests/unit/test_render_cycle.py
git commit -m "feat: render the execution summary block (Phase 5)"
```

---

## Task 9: README + opt-in live review-only test + full verification

**Files:**
- Modify: `README.md`
- Test: `tests/unit/test_order_executor.py` (opt-in live review-only test)

- [ ] **Step 1: Add the README section** — `README.md`

Add a "Placing real orders (HumanApproval)" section after the "Running a strategy (DryRun)"
section. It must state: DryRun is the default; `wizard run <id> --execute` places real orders
after a typed `yes`; whole-share orders are limit (price-protected) and fractional are market
(regular hours only — run during market hours); orders go only to the agentic account; the
risk engine still vets everything first; on a place failure it halts and reports. Also update
the Status + Roadmap (Phase 5 / order execution moves to "what works today"; "Next" becomes
Autonomous mode + kill-switch).

- [ ] **Step 2: Add the opt-in live review-only test** — append to `tests/unit/test_order_executor.py`

```python
import os

import pytest


@pytest.mark.skipif(
    not (os.environ.get("RH_WIZARD_LIVE") and os.environ.get("RH_WIZARD_LIVE_EXECUTE")),
    reason="live review test: needs RH_WIZARD_LIVE=1 and RH_WIZARD_LIVE_EXECUTE=1 + a cached token",
)
def test_live_review_only_never_places(monkeypatch):
    # REVIEW ONLY — this test never calls place_equity_order.
    from rh_wizard.broker.client import make_broker_client
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.memory.portfolio import resolve_account_number
    from rh_wizard.models.plan import TradeIntent

    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        account = resolve_account_number(broker, settings)
        ex = RobinhoodOrderExecutor(broker)
        rv = ex.review(TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="1.00"), account)
        assert isinstance(rv.ok, bool)  # a ReviewResult came back; we never place
```

> During this live review, record the real `review_equity_order` response shape (alerts +
> estimated-cost fields) in the main spec §18, and confirm `_parse_alerts`/`_parse_order_id`
> match — adjust if needed before the first real `--execute` run.

- [ ] **Step 3: Full verification**

Run: `uv run pytest`
Expected: all pass; only double-gated live tests skipped. Confirm no test placed a real order (grep is a good sanity check: the only `place_equity_order` call sites are `broker/client.py`, `execution/robinhood.py`, and fakes in tests).

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

Run: `uv run pytest tests/unit/test_oss_files.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md tests/unit/test_order_executor.py
git commit -m "docs: document --execute (HumanApproval) + opt-in live review test (Phase 5)"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage:**
- `--execute` opt-in / DryRun default / HUMAN_APPROVAL mode → Tasks 6/7. ✓
- Whole-plan typed-`yes` confirmation, no bypass → Task 4 (+ Task 7 wires it). ✓
- Order mapping (whole→limit, fractional→market, sells) → Task 3 `_order_params`. ✓
- review→place + `ref_id` + skip-on-alert + halt-on-fail → Tasks 3/6. ✓
- Agentic account only (`portfolio.account_number`) → Task 6. ✓
- Broker wrappers (forward non-None) → Task 2. ✓
- Models, journal, render → Tasks 1/5/8. ✓
- Idempotency (reconcile + ref_id + journal-each + halt) → Tasks 6 (ref_id, halt) + existing reconcile. ✓
- Safety: no order in DryRun, nothing placed without confirm, executor only acts on `vetted.approved`, live test review-only → Tasks 6/7/9. ✓
- Live-verify review/place shapes → Task 9 note + defensive parsing in Task 3. ✓

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to" — every code step shows complete code. The one deferred item (real review/place response shapes) is an explicit defensive-parse + live-verify step, matching prior phases.

**3. Type consistency:** `OrderExecutor.review(intent, account)->ReviewResult` / `place(intent, account, ref_id)->OrderResult` consistent across Tasks 3/6/7. `ApprovalGate.confirm(vetted, portfolio, account)->bool` consistent Tasks 3/4/6. `_order_params(intent)->(order_type, params)` consistent Tasks 2/3. `record_orders(run_id, orders)` consistent Tasks 5/6. `CycleResult.orders` set in Task 6, read in Task 8. `_build_executor(broker)`/`_build_approval()` consistent Tasks 7. `OrderResult.order_type` defaults `""` (skipped path in Task 6 omits it).
