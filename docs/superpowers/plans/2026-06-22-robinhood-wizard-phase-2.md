# Robinhood Wizard — Phase 2 Implementation Plan (Risk Engine)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the **risk engine** — pure, deterministic code that vets a proposed `TradePlan` against the effective `RiskPolicy` and a live `PortfolioState`, producing a `VettedPlan` (approved/rejected intents with reasons) — exhaustively unit-tested **before any execution path exists** (spec §17 Phase 2, §14 "the risk engine is the crown jewel").

**Architecture:** Pure functions, no I/O, no LLM, no broker. New Pydantic models (`RiskPolicy`, `RiskCeiling`, `TradeIntent`, `TradePlan`, `VettedPlan`, `SymbolRisk`); `risk/policy.py` merges per-strategy overrides onto global defaults and clamps the result to an optional global hard-ceiling; `risk/engine.py` `vet()` walks the plan's intents in order, accumulating against cash/spend caps, and buckets each intent into approved or rejected. The LLM cannot bypass it because it is plain code the deterministic cycle runs after plan generation.

**Tech Stack:** Python 3.12, `pydantic` v2, `Decimal` for all money/quantities/percentages, `pytest`, `ruff`, `uv`. No new third-party dependencies.

## Design Decisions (review these — flag if you disagree)

These resolve ambiguities in the spec's *indicative* interfaces (§6 says signatures are "finalized during implementation"):

1. **`vet` takes a pure `market` input.** The spec's indicative `vet(plan, policy, portfolio)` cannot enforce the liquidity floor (needs price / avg-volume / market-cap) or slippage band (needs current price). So the signature is `vet(plan, policy, portfolio, market)` where `market: dict[str, SymbolRisk]` is **passed in, not fetched** — the engine stays pure (no I/O) and *every* guardrail is fully testable now (§14). Phase 3's data layer will supply `market` from its `MarketContext`.
2. **Approve / reject only (no adjustment in v1).** `VettedPlan` has an `adjusted` bucket (spec §7), but v1 leaves it empty and never resizes an intent — an intent that violates any guardrail is **rejected** with a reason. This makes the safety property "no approved order ever exceeds the effective `RiskPolicy`" correct by construction. Auto-adjustment (shrinking an oversized buy to fit) is a deliberate future enhancement; `adjusted` is a documented forward-seam.
3. **Kill-switch threshold is carried, not enforced here.** `RiskPolicy.drawdown_kill_switch_pct` exists, but the drawdown halt is a cycle-level step (spec §8 step 4) that needs the high-water mark from `PerformanceTracker` — both are Phase 6. Phase 2 does not enforce it.
4. **Sells are exempt from buy-only guardrails.** A sell reduces exposure and frees cash, so it is not subject to position-cap / cash-reserve / deploy-cap / liquidity-floor checks. Sells are still subject to: valid side, limit-price present, trades-per-cycle, slippage band, and a "can't sell more than held" check.
5. **Percentages are `Decimal` whole numbers.** `max_position_pct = Decimal("20")` means 20%. All comparisons compute `part / whole * 100` and compare to the policy's percent value.

---

## Global Constraints

Every task implicitly includes these:

- **Python:** `requires-python = ">=3.12"`; ruff `target-version = "py312"`.
- **Lint/format:** `ruff` `select = ["E", "F", "I", "UP", "B"]`, `line-length = 100`. Every task ends green on `uv run ruff check .` and `uv run ruff format --check .`.
- **Tests:** `uv run pytest` (configured `-q`, `pythonpath = ["src"]`). The risk engine is **the crown jewel** — table-driven tests for **every** guardrail (spec §14). No network/LLM/broker in any of these tests; everything is pure.
- **Money/quantities/percentages are `Decimal`.** Never `float`. Construct from strings in tests (`Decimal("20")`).
- **The risk engine is pure: no I/O, no imports of `broker/`, `auth/`, `memory/`, `cli/`, or `llm/`.** It depends only on `models/` and the stdlib. A test asserts this.
- **Safety property (spec §14):** no intent in `VettedPlan.approved` may exceed any dial of the effective `RiskPolicy`.
- **Effective policy = strategy overrides merged onto global defaults, then clamped to an optional global hard-ceiling** (spec §9). Conservative defaults (spec §9, ~$3,000 account): max 20% per position, ≥10% cash reserve, ≤5 trades/cycle, ≤30% deployed/cycle, ≤0.5% slippage band, liquidity floor (price ≥ $5, avg volume ≥ 1M shares, market cap ≥ $1B), drawdown kill-switch 15%.
- **Models use `pydantic.BaseModel` with `from __future__ import annotations`**; input models that should reject typos use `model_config = pydantic.ConfigDict(extra="forbid")`.

**Branch:** Create `phase-2` off `main` (after PR #2 / the `mask_account` relocation is merged). Open a PR at the end. No live verification is needed — Phase 2 is entirely pure and unit-tested.

---

## File Structure

**New files:**
- `src/rh_wizard/models/risk.py` — `RiskPolicy`, `RiskCeiling`.
- `src/rh_wizard/models/plan.py` — `TradeIntent`, `TradePlan`, `RejectedIntent`, `VettedPlan`.
- `src/rh_wizard/models/market.py` — `SymbolRisk` (the pure per-symbol market input to the engine).
- `src/rh_wizard/risk/__init__.py` — new `risk/` package.
- `src/rh_wizard/risk/policy.py` — `effective_policy`, `apply_ceiling`, `build_effective_policy`.
- `src/rh_wizard/risk/engine.py` — `vet`, `VetContext`, guardrail checks.
- `tests/unit/test_models_risk.py`, `test_models_plan.py`, `test_risk_policy.py`, `test_risk_engine.py`, `test_risk_engine_sells.py`, `test_risk_config.py`, `test_risk_safety_properties.py`, `test_risk_engine_purity.py`

**Modified files:**
- `src/rh_wizard/config/settings.py` — add `risk: RiskPolicy` + `risk_ceiling: RiskCeiling | None`.
- `config.example.yaml` — document the `risk:` block.

---

### Task 1: Risk models — `RiskPolicy` and `RiskCeiling`

The per-strategy guardrail dials (spec §7/§9) and the optional global hard-ceiling that bounds overrides.

**Files:**
- Create: `src/rh_wizard/models/risk.py`
- Create: `tests/unit/test_models_risk.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `RiskPolicy(max_position_pct, cash_reserve_pct, max_trades_per_cycle, max_deploy_pct_per_cycle, slippage_band_pct, min_price, min_avg_volume, min_market_cap, drawdown_kill_switch_pct)` — all `Decimal` except `max_trades_per_cycle: int`, with the §9 defaults; `extra="forbid"`.
  - `RiskCeiling(max_position_pct, min_cash_reserve_pct, max_trades_per_cycle, max_deploy_pct_per_cycle, max_slippage_band_pct, min_price_floor, min_avg_volume_floor, min_market_cap_floor, max_drawdown_kill_switch_pct)` — every field `... | None = None`; `extra="forbid"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_risk.py
from decimal import Decimal

from rh_wizard.models.risk import RiskCeiling, RiskPolicy


def test_riskpolicy_conservative_defaults():
    p = RiskPolicy()
    assert p.max_position_pct == Decimal("20")
    assert p.cash_reserve_pct == Decimal("10")
    assert p.max_trades_per_cycle == 5
    assert p.max_deploy_pct_per_cycle == Decimal("30")
    assert p.slippage_band_pct == Decimal("0.5")
    assert p.min_price == Decimal("5")
    assert p.min_avg_volume == Decimal("1000000")
    assert p.min_market_cap == Decimal("1000000000")
    assert p.drawdown_kill_switch_pct == Decimal("15")


def test_riskpolicy_coerces_and_forbids_extra():
    import pydantic
    import pytest

    p = RiskPolicy(max_position_pct="25")
    assert p.max_position_pct == Decimal("25")
    with pytest.raises(pydantic.ValidationError):
        RiskPolicy(unknown_field=1)


def test_riskceiling_fields_default_none():
    c = RiskCeiling()
    assert c.max_position_pct is None
    assert c.min_cash_reserve_pct is None
    assert c.max_drawdown_kill_switch_pct is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_risk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.risk'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/risk.py
"""Risk guardrail models (spec §7/§9).

``RiskPolicy`` holds the per-strategy dials with conservative defaults tuned for a
~$3,000 account. ``RiskCeiling`` is the optional global hard-ceiling: it bounds what any
strategy override may set, so a typo can't (e.g.) push max-position to 100%.
Percentages are whole-number Decimals (``Decimal("20")`` == 20%).
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class RiskPolicy(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    max_position_pct: Decimal = Decimal("20")  # max % of portfolio value per position
    cash_reserve_pct: Decimal = Decimal("10")  # min % of portfolio kept as cash
    max_trades_per_cycle: int = 5
    max_deploy_pct_per_cycle: Decimal = Decimal("30")  # max % of portfolio bought per cycle
    slippage_band_pct: Decimal = Decimal("0.5")  # max |limit - market| / market, percent
    min_price: Decimal = Decimal("5")  # liquidity floor: min share price
    min_avg_volume: Decimal = Decimal("1000000")  # liquidity floor: min avg daily volume
    min_market_cap: Decimal = Decimal("1000000000")  # liquidity floor: min market cap
    drawdown_kill_switch_pct: Decimal = Decimal("15")  # halt threshold (enforced in Phase 6)


class RiskCeiling(pydantic.BaseModel):
    """Optional global bounds on an effective policy. Only set fields are clamped."""

    model_config = pydantic.ConfigDict(extra="forbid")

    max_position_pct: Decimal | None = None  # clamp policy.max_position_pct DOWN to this
    min_cash_reserve_pct: Decimal | None = None  # clamp policy.cash_reserve_pct UP to this
    max_trades_per_cycle: int | None = None
    max_deploy_pct_per_cycle: Decimal | None = None
    max_slippage_band_pct: Decimal | None = None
    min_price_floor: Decimal | None = None  # clamp policy.min_price UP to this
    min_avg_volume_floor: Decimal | None = None  # clamp policy.min_avg_volume UP
    min_market_cap_floor: Decimal | None = None  # clamp policy.min_market_cap UP
    max_drawdown_kill_switch_pct: Decimal | None = None  # clamp policy.drawdown DOWN
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_risk.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/risk.py tests/unit/test_models_risk.py
git commit -m "feat: add RiskPolicy and RiskCeiling models"
```

---

### Task 2: Plan + market models — `TradeIntent`, `TradePlan`, `VettedPlan`, `SymbolRisk`

The engine's inputs (the proposed plan + per-symbol market facts) and output (the vetted plan).

**Files:**
- Create: `src/rh_wizard/models/plan.py`
- Create: `src/rh_wizard/models/market.py`
- Create: `tests/unit/test_models_plan.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `TradeIntent(side: str, symbol: str, quantity: Decimal | None = None, amount: Decimal | None = None, limit_price: Decimal | None = None, rationale: str = "", confidence: Decimal | None = None)`
  - `TradePlan(intents: list[TradeIntent], rationale: str = "")`
  - `RejectedIntent(intent: TradeIntent, reason: str)`
  - `VettedPlan(approved: list[TradeIntent] = [], adjusted: list[TradeIntent] = [], rejected: list[RejectedIntent] = [])`
  - `SymbolRisk(symbol: str, price: Decimal, average_volume: Decimal | None = None, market_cap: Decimal | None = None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_plan.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import RejectedIntent, TradeIntent, TradePlan, VettedPlan


def test_trade_intent_coerces_decimals():
    i = TradeIntent(side="buy", symbol="AAPL", quantity="10", limit_price="190.50")
    assert i.quantity == Decimal("10")
    assert i.limit_price == Decimal("190.50")
    assert i.amount is None


def test_trade_plan_holds_intents():
    plan = TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL")], rationale="thesis")
    assert len(plan.intents) == 1
    assert plan.rationale == "thesis"


def test_vetted_plan_buckets_default_empty():
    v = VettedPlan()
    assert v.approved == []
    assert v.adjusted == []
    assert v.rejected == []


def test_rejected_intent_carries_reason():
    r = RejectedIntent(intent=TradeIntent(side="buy", symbol="AAPL"), reason="too big")
    assert r.reason == "too big"
    assert r.intent.symbol == "AAPL"


def test_symbol_risk_fields():
    s = SymbolRisk(symbol="AAPL", price="190.00", average_volume="50000000", market_cap="3.0E12")
    assert s.price == Decimal("190.00")
    assert s.average_volume == Decimal("50000000")
    assert s.market_cap == Decimal("3.0E12")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.plan'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/market.py
"""Per-symbol market facts the risk engine needs (spec §11).

A pure value object passed into the risk engine so it can check the liquidity floor and
slippage band without doing any I/O. Phase 3's data layer will populate these.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class SymbolRisk(pydantic.BaseModel):
    symbol: str
    price: Decimal  # current/last market price
    average_volume: Decimal | None = None  # average daily share volume
    market_cap: Decimal | None = None
```

```python
# src/rh_wizard/models/plan.py
"""Trade plan + vetting models (spec §7).

A ``TradePlan`` is the LLM's proposed output (ordered ``TradeIntent``s). The risk engine
turns it into a ``VettedPlan`` (approved / rejected, with reasons). ``adjusted`` is a
forward-seam for future auto-resizing — empty in Phase 2.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class TradeIntent(pydantic.BaseModel):
    side: str  # "buy" | "sell"
    symbol: str
    quantity: Decimal | None = None  # target share quantity (or use ``amount``)
    amount: Decimal | None = None  # target dollar amount (alternative to ``quantity``)
    limit_price: Decimal | None = None
    rationale: str = ""
    confidence: Decimal | None = None


class TradePlan(pydantic.BaseModel):
    intents: list[TradeIntent] = []
    rationale: str = ""


class RejectedIntent(pydantic.BaseModel):
    intent: TradeIntent
    reason: str


class VettedPlan(pydantic.BaseModel):
    approved: list[TradeIntent] = []
    adjusted: list[TradeIntent] = []  # forward-seam; always empty in Phase 2
    rejected: list[RejectedIntent] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_plan.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/market.py src/rh_wizard/models/plan.py tests/unit/test_models_plan.py
git commit -m "feat: add TradeIntent/TradePlan/VettedPlan and SymbolRisk models"
```

---

### Task 3: Effective policy — merge overrides onto defaults

`effective_policy(defaults, overrides)` produces the per-strategy policy by layering a partial override mapping onto the global defaults, re-validating types and rejecting unknown keys.

**Files:**
- Create: `src/rh_wizard/risk/__init__.py` (empty)
- Create: `src/rh_wizard/risk/policy.py`
- Create: `tests/unit/test_risk_policy.py`

**Interfaces:**
- Consumes: `RiskPolicy` (Task 1).
- Produces (in `risk/policy.py`):
  - `effective_policy(defaults: RiskPolicy, overrides: Mapping[str, object] | None = None) -> RiskPolicy`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_risk_policy.py
from decimal import Decimal

import pydantic
import pytest

from rh_wizard.models.risk import RiskPolicy
from rh_wizard.risk.policy import effective_policy


def test_no_overrides_returns_defaults():
    defaults = RiskPolicy()
    assert effective_policy(defaults, None) == defaults
    assert effective_policy(defaults, {}) == defaults


def test_override_replaces_only_named_fields():
    defaults = RiskPolicy()
    eff = effective_policy(defaults, {"max_position_pct": "10", "max_trades_per_cycle": 2})
    assert eff.max_position_pct == Decimal("10")
    assert eff.max_trades_per_cycle == 2
    # untouched fields keep defaults
    assert eff.cash_reserve_pct == Decimal("10")


def test_unknown_override_key_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        effective_policy(RiskPolicy(), {"nonsense": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.risk'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/risk/__init__.py
```

```python
# src/rh_wizard/risk/policy.py
"""Compose the effective RiskPolicy: strategy overrides merged onto global defaults,
then clamped to an optional global hard-ceiling (spec §9).

Pure functions — no I/O, no config import. Callers pass the defaults/ceiling in.
"""

from __future__ import annotations

from collections.abc import Mapping

from rh_wizard.models.risk import RiskCeiling, RiskPolicy


def effective_policy(
    defaults: RiskPolicy, overrides: Mapping[str, object] | None = None
) -> RiskPolicy:
    """Layer ``overrides`` onto ``defaults``. Re-validates types and rejects unknown keys
    (RiskPolicy is ``extra="forbid"``)."""
    if not overrides:
        return defaults
    return RiskPolicy(**{**defaults.model_dump(), **dict(overrides)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_policy.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/risk/__init__.py src/rh_wizard/risk/policy.py tests/unit/test_risk_policy.py
git commit -m "feat: add effective_policy (overrides merged onto defaults)"
```

---

### Task 4: Hard-ceiling clamp + `build_effective_policy`

`apply_ceiling` bounds an effective policy so an override can't weaken safety (e.g. push max-position above the ceiling or the kill-switch above its max). `build_effective_policy` composes merge + clamp.

**Files:**
- Modify: `src/rh_wizard/risk/policy.py`
- Modify: `tests/unit/test_risk_policy.py`

**Interfaces:**
- Consumes: `RiskPolicy`, `RiskCeiling` (Task 1), `effective_policy` (Task 3).
- Produces (in `risk/policy.py`):
  - `apply_ceiling(policy: RiskPolicy, ceiling: RiskCeiling | None) -> RiskPolicy`
  - `build_effective_policy(defaults: RiskPolicy, ceiling: RiskCeiling | None = None, overrides: Mapping[str, object] | None = None) -> RiskPolicy`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_risk_policy.py`:

```python
from rh_wizard.models.risk import RiskCeiling
from rh_wizard.risk.policy import apply_ceiling, build_effective_policy


def test_ceiling_none_returns_policy_unchanged():
    p = RiskPolicy(max_position_pct="80")
    assert apply_ceiling(p, None) == p


def test_ceiling_clamps_max_dials_down():
    p = RiskPolicy(max_position_pct="80", max_trades_per_cycle=50, slippage_band_pct="5")
    c = RiskCeiling(
        max_position_pct="25", max_trades_per_cycle=10, max_slippage_band_pct="1"
    )
    clamped = apply_ceiling(p, c)
    assert clamped.max_position_pct == Decimal("25")
    assert clamped.max_trades_per_cycle == 10
    assert clamped.slippage_band_pct == Decimal("1")


def test_ceiling_clamps_min_dials_up():
    p = RiskPolicy(cash_reserve_pct="0", min_price="1", min_market_cap="0")
    c = RiskCeiling(min_cash_reserve_pct="10", min_price_floor="5", min_market_cap_floor="1000000000")
    clamped = apply_ceiling(p, c)
    assert clamped.cash_reserve_pct == Decimal("10")
    assert clamped.min_price == Decimal("5")
    assert clamped.min_market_cap == Decimal("1000000000")


def test_ceiling_clamps_drawdown_down():
    # A safer kill-switch trips SOONER (smaller %). Ceiling caps it at the max allowed.
    p = RiskPolicy(drawdown_kill_switch_pct="90")
    c = RiskCeiling(max_drawdown_kill_switch_pct="20")
    assert apply_ceiling(p, c).drawdown_kill_switch_pct == Decimal("20")


def test_ceiling_does_not_tighten_already_safe_values():
    p = RiskPolicy(max_position_pct="10")  # already below the ceiling
    c = RiskCeiling(max_position_pct="25")
    assert apply_ceiling(p, c).max_position_pct == Decimal("10")


def test_build_effective_policy_merges_then_clamps():
    defaults = RiskPolicy()
    ceiling = RiskCeiling(max_position_pct="25")
    eff = build_effective_policy(defaults, ceiling, {"max_position_pct": "90"})
    assert eff.max_position_pct == Decimal("25")  # override 90 clamped to ceiling 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_policy.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_ceiling'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/rh_wizard/risk/policy.py`:

```python
def apply_ceiling(policy: RiskPolicy, ceiling: RiskCeiling | None) -> RiskPolicy:
    """Clamp an effective policy to the global hard-ceiling so overrides can't weaken
    safety. ``None`` ceiling = disabled (return policy unchanged)."""
    if ceiling is None:
        return policy
    updates: dict[str, object] = {}

    # "max" dials: an override must not exceed the ceiling — clamp DOWN.
    if ceiling.max_position_pct is not None:
        updates["max_position_pct"] = min(policy.max_position_pct, ceiling.max_position_pct)
    if ceiling.max_trades_per_cycle is not None:
        updates["max_trades_per_cycle"] = min(
            policy.max_trades_per_cycle, ceiling.max_trades_per_cycle
        )
    if ceiling.max_deploy_pct_per_cycle is not None:
        updates["max_deploy_pct_per_cycle"] = min(
            policy.max_deploy_pct_per_cycle, ceiling.max_deploy_pct_per_cycle
        )
    if ceiling.max_slippage_band_pct is not None:
        updates["slippage_band_pct"] = min(
            policy.slippage_band_pct, ceiling.max_slippage_band_pct
        )
    if ceiling.max_drawdown_kill_switch_pct is not None:
        updates["drawdown_kill_switch_pct"] = min(
            policy.drawdown_kill_switch_pct, ceiling.max_drawdown_kill_switch_pct
        )

    # "min/floor" dials: an override must not go below the floor — clamp UP.
    if ceiling.min_cash_reserve_pct is not None:
        updates["cash_reserve_pct"] = max(
            policy.cash_reserve_pct, ceiling.min_cash_reserve_pct
        )
    if ceiling.min_price_floor is not None:
        updates["min_price"] = max(policy.min_price, ceiling.min_price_floor)
    if ceiling.min_avg_volume_floor is not None:
        updates["min_avg_volume"] = max(policy.min_avg_volume, ceiling.min_avg_volume_floor)
    if ceiling.min_market_cap_floor is not None:
        updates["min_market_cap"] = max(
            policy.min_market_cap, ceiling.min_market_cap_floor
        )

    return policy.model_copy(update=updates)


def build_effective_policy(
    defaults: RiskPolicy,
    ceiling: RiskCeiling | None = None,
    overrides: Mapping[str, object] | None = None,
) -> RiskPolicy:
    """Strategy overrides merged onto defaults, then clamped to the global hard-ceiling."""
    return apply_ceiling(effective_policy(defaults, overrides), ceiling)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_policy.py -v`
Expected: PASS (9 tests in the file).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/risk/policy.py tests/unit/test_risk_policy.py
git commit -m "feat: add hard-ceiling clamp and build_effective_policy"
```

---

### Task 5: Risk engine — pipeline + per-intent checks (side, limit price, trades/cycle, slippage)

Establish `vet()`, the `VetContext` accumulator, the order-value helper, and the checks that apply to **every** intent (buy or sell): valid side, limit price present, trades-per-cycle cap, and the slippage band. Sizing/liquidity (buys) and sell-specifics come in Tasks 6–7.

**Files:**
- Create: `src/rh_wizard/risk/engine.py`
- Create: `tests/unit/test_risk_engine.py`

**Interfaces:**
- Consumes: `RiskPolicy` (Task 1), `TradeIntent`/`TradePlan`/`RejectedIntent`/`VettedPlan` (Task 2), `SymbolRisk` (Task 2), `PortfolioState` (`rh_wizard.models.portfolio`, Phase 1).
- Produces (in `risk/engine.py`):
  - `vet(plan: TradePlan, policy: RiskPolicy, portfolio: PortfolioState, market: dict[str, SymbolRisk]) -> VettedPlan`
  - `VetContext` (dataclass) and `_order_value(intent) -> Decimal | None`, `_portfolio_value(portfolio) -> Decimal`, `_build_context(...)`, `_apply_approval(intent, ctx, value)`.
  - The combined reason resolver `_reason_to_reject(intent, value, ctx) -> str | None` (extended in Tasks 6–7).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_risk_engine.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.risk.engine import vet


def _portfolio(cash="10000", total="10000", positions=None):
    return PortfolioState(
        account_number="ACC1",
        positions=positions or [],
        cash=Decimal(cash),
        buying_power=Decimal(cash),
        total_value=Decimal(total),
    )


def _market(symbol="AAPL", price="100", volume="50000000", cap="3000000000000"):
    return {symbol: SymbolRisk(symbol=symbol, price=Decimal(price),
                               average_volume=Decimal(volume), market_cap=Decimal(cap))}


def test_valid_buy_within_band_is_approved():
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", quantity="10", limit_price="100.20")
    ])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert [i.symbol for i in result.approved] == ["AAPL"]
    assert result.rejected == []
    assert result.adjusted == []  # never adjusts in v1


def test_invalid_side_rejected():
    plan = TradePlan(intents=[TradeIntent(side="hold", symbol="AAPL", limit_price="100")])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert result.approved == []
    assert "side" in result.rejected[0].reason.lower()


def test_missing_limit_price_rejected():
    plan = TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL", quantity="1")])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "limit" in result.rejected[0].reason.lower()


def test_slippage_band_rejects_far_limit():
    # market 100, limit 101 = 1% > 0.5% band
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="101")
    ])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "slippage" in result.rejected[0].reason.lower()


def test_trades_per_cycle_caps_approvals():
    # 6 small valid buys, policy allows 5; the 6th is rejected for the trade cap.
    intents = [
        TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100")
        for _ in range(6)
    ]
    result = vet(TradePlan(intents=intents), RiskPolicy(), _portfolio(), _market())
    assert len(result.approved) == 5
    assert len(result.rejected) == 1
    assert "trades" in result.rejected[0].reason.lower()


def test_no_market_data_rejected():
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="ZZZZ", quantity="1", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())  # market has AAPL only
    assert "market data" in result.rejected[0].reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.risk.engine'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/risk/engine.py
"""The risk engine (spec §6/§9/§14) — pure, deterministic, no I/O.

``vet`` walks a TradePlan's intents in order, accumulating spend/cash against the policy
caps, and buckets each intent into approved or rejected (with a reason). It is the
integrity gate the LLM cannot bypass: plain code the deterministic cycle runs after plan
generation. v1 never adjusts an intent — anything that violates a guardrail is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import RejectedIntent, TradeIntent, TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy

_BUY = "buy"
_SELL = "sell"


@dataclass
class VetContext:
    policy: RiskPolicy
    portfolio_value: Decimal
    market: dict[str, SymbolRisk]
    running_cash: Decimal
    deployed: Decimal = Decimal("0")
    approved_count: int = 0
    held_value: dict[str, Decimal] = field(default_factory=dict)
    held_qty: dict[str, Decimal] = field(default_factory=dict)


def _portfolio_value(portfolio: PortfolioState) -> Decimal:
    if portfolio.total_value is not None:
        return portfolio.total_value
    held = sum(
        (p.market_value if p.market_value is not None else p.cost_basis)
        for p in portfolio.positions
    )
    return portfolio.cash + Decimal(held)


def _order_value(intent: TradeIntent) -> Decimal | None:
    """Dollar size of an intent: explicit amount, else quantity * limit_price."""
    if intent.amount is not None:
        return intent.amount
    if intent.quantity is not None and intent.limit_price is not None:
        return intent.quantity * intent.limit_price
    return None


def _build_context(
    policy: RiskPolicy, portfolio: PortfolioState, market: dict[str, SymbolRisk]
) -> VetContext:
    held_value: dict[str, Decimal] = {}
    held_qty: dict[str, Decimal] = {}
    for p in portfolio.positions:
        held_value[p.symbol] = p.market_value if p.market_value is not None else p.cost_basis
        held_qty[p.symbol] = p.quantity
    return VetContext(
        policy=policy,
        portfolio_value=_portfolio_value(portfolio),
        market=market,
        running_cash=portfolio.cash,
        held_value=held_value,
        held_qty=held_qty,
    )


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return part / whole * 100


def _reason_to_reject(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> str | None:
    # --- checks that apply to every intent (buy or sell) ---
    if intent.side not in (_BUY, _SELL):
        return f"invalid side '{intent.side}' (must be buy or sell)"
    if intent.limit_price is None or intent.limit_price <= 0:
        return "limit price required (all orders are limit orders)"
    if ctx.approved_count >= ctx.policy.max_trades_per_cycle:
        return f"exceeds max trades per cycle ({ctx.policy.max_trades_per_cycle})"
    sym = ctx.market.get(intent.symbol)
    if sym is None:
        return f"no market data for {intent.symbol}"
    deviation = _pct(abs(intent.limit_price - sym.price), sym.price)
    if deviation > ctx.policy.slippage_band_pct:
        return (
            f"limit price {deviation:.2f}% off market exceeds slippage band "
            f"{ctx.policy.slippage_band_pct}%"
        )
    return None


def _apply_approval(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> None:
    ctx.approved_count += 1


def vet(
    plan: TradePlan,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: dict[str, SymbolRisk],
) -> VettedPlan:
    ctx = _build_context(policy, portfolio, market)
    approved: list[TradeIntent] = []
    rejected: list[RejectedIntent] = []
    for intent in plan.intents:
        value = _order_value(intent)
        reason = _reason_to_reject(intent, value, ctx)
        if reason is not None:
            rejected.append(RejectedIntent(intent=intent, reason=reason))
            continue
        approved.append(intent)
        _apply_approval(intent, value, ctx)
    return VettedPlan(approved=approved, adjusted=[], rejected=rejected)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_engine.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/risk/engine.py tests/unit/test_risk_engine.py
git commit -m "feat: risk engine pipeline + per-intent checks (side/limit/trades/slippage)"
```

---

### Task 6: Risk engine — buy guardrails (liquidity floor, position cap, cash reserve, deploy cap)

Add the buy-only money guardrails with sequential accumulation: a buy must clear the liquidity floor, keep the position within `max_position_pct`, keep cash at/above the reserve, and keep cumulative deployment within `max_deploy_pct_per_cycle`. Approved buys decrement running cash and increment deployed/held.

**Files:**
- Modify: `src/rh_wizard/risk/engine.py`
- Modify: `tests/unit/test_risk_engine.py`

**Interfaces:**
- Consumes: everything from Task 5.
- Produces: extended `_reason_to_reject` (adds buy checks via `_buy_reason`) and `_apply_approval` (updates cash/deployed/held for buys). No signature changes.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_risk_engine.py`:

```python
def test_position_cap_rejects_oversized_buy():
    # portfolio 10000, max 20% => $2000 cap; buy 30 * 100 = 3000 > 2000
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", quantity="30", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "position" in result.rejected[0].reason.lower()


def test_position_cap_counts_existing_holding():
    from rh_wizard.models.portfolio import Position

    held = Position(symbol="AAPL", quantity="15", average_cost="100",
                    cost_basis="1500", market_value="1500")
    # cash 8500 + position 1500 = 10000 total; existing 1500 + buy 600 = 2100 > 2000 (20%)
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", quantity="6", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio(cash="8500", positions=[held]), _market())
    assert "position" in result.rejected[0].reason.lower()


def test_cash_reserve_rejects_buy_that_breaches_reserve():
    # Raise position + deploy caps so ONLY the cash reserve can trip:
    # portfolio 10000, reserve 10% => keep >= 1000; buy 9500 leaves 500 < 1000.
    policy = RiskPolicy(max_position_pct="100", max_deploy_pct_per_cycle="100")
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", amount="9500", quantity="95", limit_price="100")
    ])
    result = vet(plan, policy, _portfolio(), _market())
    assert "cash reserve" in result.rejected[0].reason.lower()


def test_deploy_cap_rejects_cumulative_overspend():
    # max_deploy 30% of 10000 = 3000. Two buys of 2000 each: second pushes to 4000 > 3000.
    # Raise position cap so position-sizing doesn't reject first (each 2000 = 20% exactly OK).
    policy = RiskPolicy(max_position_pct="100", cash_reserve_pct="0")
    intents = [
        TradeIntent(side="buy", symbol="AAPL", quantity="20", limit_price="100"),
        TradeIntent(side="buy", symbol="MSFT", quantity="20", limit_price="100"),
    ]
    market = {**_market("AAPL"), **_market("MSFT")}
    result = vet(TradePlan(intents=intents), policy, _portfolio(), market)
    assert len(result.approved) == 1
    assert "deploy" in result.rejected[0].reason.lower()


def test_liquidity_floor_rejects_penny_stock():
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="PNY", quantity="1", limit_price="2")
    ])
    market = _market("PNY", price="2")  # price 2 < min_price 5
    result = vet(plan, RiskPolicy(), _portfolio(), market)
    assert "liquidity" in result.rejected[0].reason.lower()


def test_liquidity_floor_rejects_thin_volume_and_small_cap():
    low_vol = _market("AAPL", volume="100")  # < 1M
    assert "liquidity" in vet(
        TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100")]),
        RiskPolicy(), _portfolio(), low_vol,
    ).rejected[0].reason.lower()
    small_cap = _market("AAPL", cap="100")  # < 1B
    assert "liquidity" in vet(
        TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100")]),
        RiskPolicy(), _portfolio(), small_cap,
    ).rejected[0].reason.lower()


def test_unsizable_buy_rejected():
    # no amount and no quantity => cannot size
    plan = TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL", limit_price="100")])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "size" in result.rejected[0].reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_engine.py -v`
Expected: FAIL — the oversized/penny/etc. buys are currently approved (sizing/liquidity not yet implemented).

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/risk/engine.py`, replace `_reason_to_reject` and `_apply_approval` with these complete versions (adds the `_buy_reason` helper and buy accumulation):

```python
def _buy_reason(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> str | None:
    if value is None:
        return "cannot determine order size (need amount or quantity + limit price)"
    if ctx.portfolio_value <= 0:
        return "portfolio value must be positive to size a buy"
    sym = ctx.market[intent.symbol]  # presence already checked by caller

    # Liquidity floor (spec §9).
    if sym.price < ctx.policy.min_price:
        return f"liquidity floor: price {sym.price} below min {ctx.policy.min_price}"
    if sym.average_volume is None or sym.average_volume < ctx.policy.min_avg_volume:
        return f"liquidity floor: avg volume below min {ctx.policy.min_avg_volume}"
    if sym.market_cap is None or sym.market_cap < ctx.policy.min_market_cap:
        return f"liquidity floor: market cap below min {ctx.policy.min_market_cap}"

    # Position cap: existing holding + this buy must stay within max_position_pct.
    prospective_position = ctx.held_value.get(intent.symbol, Decimal("0")) + value
    if _pct(prospective_position, ctx.portfolio_value) > ctx.policy.max_position_pct:
        return f"would exceed max position {ctx.policy.max_position_pct}% of portfolio"

    # Cash reserve: cash after the buy must stay at/above the reserve floor.
    reserve_floor = ctx.portfolio_value * ctx.policy.cash_reserve_pct / 100
    if ctx.running_cash - value < reserve_floor:
        return f"would breach cash reserve of {ctx.policy.cash_reserve_pct}%"

    # Per-cycle deploy cap: cumulative buys must stay within max_deploy_pct_per_cycle.
    if _pct(ctx.deployed + value, ctx.portfolio_value) > ctx.policy.max_deploy_pct_per_cycle:
        return f"would exceed per-cycle deploy cap of {ctx.policy.max_deploy_pct_per_cycle}%"
    return None


def _reason_to_reject(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> str | None:
    # --- checks that apply to every intent (buy or sell) ---
    if intent.side not in (_BUY, _SELL):
        return f"invalid side '{intent.side}' (must be buy or sell)"
    if intent.limit_price is None or intent.limit_price <= 0:
        return "limit price required (all orders are limit orders)"
    if ctx.approved_count >= ctx.policy.max_trades_per_cycle:
        return f"exceeds max trades per cycle ({ctx.policy.max_trades_per_cycle})"
    sym = ctx.market.get(intent.symbol)
    if sym is None:
        return f"no market data for {intent.symbol}"
    deviation = _pct(abs(intent.limit_price - sym.price), sym.price)
    if deviation > ctx.policy.slippage_band_pct:
        return (
            f"limit price {deviation:.2f}% off market exceeds slippage band "
            f"{ctx.policy.slippage_band_pct}%"
        )
    # --- buy-only money guardrails ---
    if intent.side == _BUY:
        return _buy_reason(intent, value, ctx)
    return None


def _apply_approval(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> None:
    ctx.approved_count += 1
    if intent.side == _BUY and value is not None:
        ctx.running_cash -= value
        ctx.deployed += value
        ctx.held_value[intent.symbol] = ctx.held_value.get(intent.symbol, Decimal("0")) + value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_engine.py -v`
Expected: PASS (13 tests in the file).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/risk/engine.py tests/unit/test_risk_engine.py
git commit -m "feat: risk engine buy guardrails (liquidity, position, cash, deploy)"
```

---

### Task 7: Risk engine — sells handling

Sells are exempt from buy-only guardrails (they reduce exposure and free cash), but must still pass side/limit/trades/slippage and a "can't sell more than held" check. Approved sells free cash and reduce the held position.

**Files:**
- Modify: `src/rh_wizard/risk/engine.py`
- Create: `tests/unit/test_risk_engine_sells.py`

**Interfaces:**
- Consumes: everything from Tasks 5–6.
- Produces: a `_sell_reason` branch in `_reason_to_reject` and sell accumulation in `_apply_approval`. No signature changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_risk_engine_sells.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import Position, PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.risk.engine import vet


def _market(symbol="AAPL", price="100"):
    return {symbol: SymbolRisk(symbol=symbol, price=Decimal(price),
                               average_volume=Decimal("50000000"),
                               market_cap=Decimal("3000000000000"))}


def _portfolio_with_holding(qty="10"):
    held = Position(symbol="AAPL", quantity=qty, average_cost="100",
                    cost_basis=str(Decimal(qty) * Decimal("100")),
                    market_value=str(Decimal(qty) * Decimal("100")))
    return PortfolioState(account_number="ACC1", positions=[held],
                          cash=Decimal("0"), buying_power=Decimal("0"),
                          total_value=str(Decimal(qty) * Decimal("100")))


def test_sell_within_holding_is_approved():
    plan = TradePlan(intents=[
        TradeIntent(side="sell", symbol="AAPL", quantity="5", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(), _market())
    assert [i.symbol for i in result.approved] == ["AAPL"]


def test_sell_more_than_held_rejected():
    plan = TradePlan(intents=[
        TradeIntent(side="sell", symbol="AAPL", quantity="20", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(qty="10"), _market())
    assert "held" in result.rejected[0].reason.lower()


def test_sell_exempt_from_cash_reserve_and_deploy():
    # No cash, reserve 10% — a sell must still be allowed (it raises cash, not spends it).
    plan = TradePlan(intents=[
        TradeIntent(side="sell", symbol="AAPL", quantity="10", limit_price="100")
    ])
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(qty="10"), _market())
    assert len(result.approved) == 1
    assert result.rejected == []


def test_sell_still_subject_to_slippage():
    plan = TradePlan(intents=[
        TradeIntent(side="sell", symbol="AAPL", quantity="5", limit_price="90")  # 10% off
    ])
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(), _market())
    assert "slippage" in result.rejected[0].reason.lower()


def test_sell_frees_cash_for_a_following_buy():
    # Hold 10 AAPL ($1000), no cash. Sell 10 (frees ~$1000), then buy MSFT $500.
    # Without the freed cash the buy would breach the reserve.
    policy = RiskPolicy(cash_reserve_pct="0", max_deploy_pct_per_cycle="100", max_position_pct="100")
    market = {**_market("AAPL"), **_market("MSFT")}
    intents = [
        TradeIntent(side="sell", symbol="AAPL", quantity="10", limit_price="100"),
        TradeIntent(side="buy", symbol="MSFT", quantity="5", limit_price="100"),
    ]
    result = vet(TradePlan(intents=intents), policy, _portfolio_with_holding(qty="10"), market)
    assert {i.symbol for i in result.approved} == {"AAPL", "MSFT"}
    assert result.rejected == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_engine_sells.py -v`
Expected: FAIL — `test_sell_more_than_held_rejected` fails (the held check doesn't exist yet) and/or the freed-cash buy is rejected.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/risk/engine.py`, add a `_sell_reason` helper and wire sells into `_reason_to_reject` and `_apply_approval`. Add this helper above `_reason_to_reject`:

```python
def _sell_reason(intent: TradeIntent, ctx: VetContext) -> str | None:
    if intent.quantity is not None:
        held = ctx.held_qty.get(intent.symbol, Decimal("0"))
        if intent.quantity > held:
            return f"cannot sell {intent.quantity} of {intent.symbol}; only {held} held"
    return None
```

Replace the side dispatch tail of `_reason_to_reject` (the `if intent.side == _BUY:` block) with:

```python
    # --- side-specific guardrails ---
    if intent.side == _BUY:
        return _buy_reason(intent, value, ctx)
    return _sell_reason(intent, ctx)
```

Replace `_apply_approval` with this complete version (adds the sell branch):

```python
def _apply_approval(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> None:
    ctx.approved_count += 1
    if intent.side == _BUY and value is not None:
        ctx.running_cash -= value
        ctx.deployed += value
        ctx.held_value[intent.symbol] = ctx.held_value.get(intent.symbol, Decimal("0")) + value
    elif intent.side == _SELL and value is not None:
        ctx.running_cash += value
        ctx.held_value[intent.symbol] = ctx.held_value.get(intent.symbol, Decimal("0")) - value
        ctx.held_qty[intent.symbol] = ctx.held_qty.get(intent.symbol, Decimal("0")) - (
            intent.quantity or Decimal("0")
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_engine_sells.py tests/unit/test_risk_engine.py -v`
Expected: PASS (both files; the Task 5/6 buy tests still pass).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/risk/engine.py tests/unit/test_risk_engine_sells.py
git commit -m "feat: risk engine sells handling (held-qty check, frees cash, exemptions)"
```

---

### Task 8: Config — default `RiskPolicy` and global hard-ceiling

Wire the global default policy and optional hard-ceiling into `Settings` (spec §5: "Global config.yaml: default RiskPolicy, global hard-ceiling"), so the cycle (later phase) can build the effective policy from config.

**Files:**
- Modify: `src/rh_wizard/config/settings.py`
- Modify: `config.example.yaml`
- Create: `tests/unit/test_risk_config.py`

**Interfaces:**
- Consumes: `RiskPolicy`, `RiskCeiling` (Task 1), `build_effective_policy` (Task 4), `load_settings` (Phase 1).
- Produces: `Settings.risk: RiskPolicy` (default = conservative defaults) and `Settings.risk_ceiling: RiskCeiling | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_risk_config.py
from decimal import Decimal

from rh_wizard.config.settings import Settings, load_settings
from rh_wizard.risk.policy import build_effective_policy


def test_settings_has_default_risk_policy():
    s = Settings()
    assert s.risk.max_position_pct == Decimal("20")
    assert s.risk_ceiling is None


def test_settings_loads_risk_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "risk:\n"
        "  max_position_pct: 15\n"
        "  max_trades_per_cycle: 3\n"
        "risk_ceiling:\n"
        "  max_position_pct: 25\n"
    )
    s = load_settings(cfg)
    assert s.risk.max_position_pct == Decimal("15")
    assert s.risk.max_trades_per_cycle == 3
    assert s.risk_ceiling.max_position_pct == Decimal("25")


def test_config_drives_effective_policy(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("risk_ceiling:\n  max_position_pct: 25\n")
    s = load_settings(cfg)
    # a reckless strategy override is clamped by the configured ceiling
    eff = build_effective_policy(s.risk, s.risk_ceiling, {"max_position_pct": "90"})
    assert eff.max_position_pct == Decimal("25")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_risk_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'risk'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/config/settings.py`, add the import and two fields to `Settings`. Add to the imports:

```python
import pydantic

from rh_wizard.models.risk import RiskCeiling, RiskPolicy
```

(Keep the existing imports; `pydantic` is already imported — don't duplicate it.) Add these fields to the `Settings` model (after `account_number`):

```python
    risk: RiskPolicy = pydantic.Field(default_factory=RiskPolicy)
    risk_ceiling: RiskCeiling | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Document the `risk` block in `config.example.yaml`**

Append to `config.example.yaml`:

```yaml

# Risk guardrails (global defaults; per-strategy overrides come later). Shown values are
# the built-in conservative defaults — uncomment/edit to change them.
# risk:
#   max_position_pct: 20          # max % of portfolio per position
#   cash_reserve_pct: 10          # min % kept as cash
#   max_trades_per_cycle: 5
#   max_deploy_pct_per_cycle: 30  # max % of portfolio bought per cycle
#   slippage_band_pct: 0.5        # max % a limit price may sit off the market
#   min_price: 5                  # liquidity floor: min share price
#   min_avg_volume: 1000000       # liquidity floor: min avg daily volume
#   min_market_cap: 1000000000    # liquidity floor: min market cap
#   drawdown_kill_switch_pct: 15  # halt threshold (enforced in a later phase)

# Optional global hard-ceiling: bounds what any strategy override may set.
# risk_ceiling:
#   max_position_pct: 30
#   min_cash_reserve_pct: 5
```

- [ ] **Step 6: Run settings/OSS tests + lint**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/test_oss_files.py tests/unit/test_risk_config.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (the `risk` example is commented placeholders, so `test_example_files_have_no_real_secrets` stays green).

- [ ] **Step 7: Commit**

```bash
git add src/rh_wizard/config/settings.py config.example.yaml tests/unit/test_risk_config.py
git commit -m "feat: add default RiskPolicy and hard-ceiling to config"
```

---

### Task 9: Safety property tests + purity guard (spec §14)

The crown-jewel assurance: adversarial/combined scenarios proving the core safety property — **no approved intent ever exceeds the effective policy** — plus a guard that the engine is import-pure (no I/O layers).

**Files:**
- Create: `tests/unit/test_risk_safety_properties.py`
- Create: `tests/unit/test_risk_engine_purity.py`

**Interfaces:**
- Consumes: `vet` (Tasks 5–7), `build_effective_policy` (Task 4), all models.
- Produces: nothing (tests only).

- [ ] **Step 1: Write the safety-property test**

```python
# tests/unit/test_risk_safety_properties.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskCeiling, RiskPolicy
from rh_wizard.risk.engine import _order_value, vet
from rh_wizard.risk.policy import build_effective_policy


def _portfolio(cash="10000"):
    return PortfolioState(account_number="ACC1", positions=[], cash=Decimal(cash),
                          buying_power=Decimal(cash), total_value=Decimal(cash))


def _market(*symbols):
    return {
        s: SymbolRisk(symbol=s, price=Decimal("100"),
                      average_volume=Decimal("50000000"),
                      market_cap=Decimal("3000000000000"))
        for s in symbols
    }


def test_no_approved_buy_exceeds_position_or_deploy_or_reserve():
    # Throw many oversized/again-and-again buys at the engine; every APPROVED buy must
    # individually respect position cap, and the set must respect cash reserve + deploy cap.
    policy = RiskPolicy()  # 20% position, 10% reserve, 30% deploy, 5 trades
    pv = Decimal("10000")
    syms = [f"S{i}" for i in range(10)]
    intents = [
        TradeIntent(side="buy", symbol=s, quantity="10", limit_price="100")  # $1000 each (10%)
        for s in syms
    ]
    result = vet(TradePlan(intents=intents), policy, _portfolio(), _market(*syms))
    assert result.approved  # some buys fit (deploy cap binds at 30% = three $1000 buys)

    # Every approved buy is within the per-position cap.
    for i in result.approved:
        assert _order_value(i) / pv * 100 <= policy.max_position_pct
    # Cumulative deploy within the cap.
    total = sum(_order_value(i) for i in result.approved)
    assert total / pv * 100 <= policy.max_deploy_pct_per_cycle
    # Cash reserve preserved.
    assert _portfolio().cash - total >= pv * policy.cash_reserve_pct / 100
    # Trade-count cap.
    assert len(result.approved) <= policy.max_trades_per_cycle


def test_ceiling_makes_reckless_override_safe():
    # A strategy tries max_position 100% and 50 trades; the ceiling forces it back.
    defaults = RiskPolicy()
    ceiling = RiskCeiling(max_position_pct="20", max_trades_per_cycle="5")
    policy = build_effective_policy(
        defaults, ceiling, {"max_position_pct": "100", "max_trades_per_cycle": 50}
    )
    assert policy.max_position_pct == Decimal("20")  # clamped down from 100
    assert policy.max_trades_per_cycle == 5  # clamped down from 50
    # A $5000 buy (50% of a $10k portfolio) would pass under the reckless 100% override,
    # but the clamped 20% policy rejects it — proving the ceiling protected us.
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="S0", quantity="50", limit_price="100")
    ])
    result = vet(plan, policy, _portfolio(), _market("S0"))
    assert result.approved == []
    assert "position" in result.rejected[0].reason.lower()


def test_empty_plan_yields_empty_vetted_plan():
    result = vet(TradePlan(intents=[]), RiskPolicy(), _portfolio(), {})
    assert result.approved == [] and result.rejected == [] and result.adjusted == []
```

- [ ] **Step 2: Run the safety-property test to verify it passes**

Run: `uv run pytest tests/unit/test_risk_safety_properties.py -v`
Expected: PASS (the engine from Tasks 5–7 already satisfies these). If any fails, the engine has a real safety bug — fix the engine, not the test.

- [ ] **Step 3: Write the purity guard test**

```python
# tests/unit/test_risk_engine_purity.py
"""The risk engine must be pure: it may not import I/O layers (broker, auth, memory, cli,
llm). It depends only on models and the stdlib."""

import ast
from pathlib import Path

FORBIDDEN = ("broker", "auth", "memory", "cli", "llm")
ENGINE_FILES = ["src/rh_wizard/risk/engine.py", "src/rh_wizard/risk/policy.py"]
ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_risk_modules_do_not_import_io_layers():
    for rel in ENGINE_FILES:
        mods = _imported_modules(ROOT / rel)
        for m in mods:
            for layer in FORBIDDEN:
                assert f"rh_wizard.{layer}" not in m, f"{rel} imports forbidden layer: {m}"
```

- [ ] **Step 4: Run the purity guard to verify it passes**

Run: `uv run pytest tests/unit/test_risk_engine_purity.py -v`
Expected: PASS (engine imports only `rh_wizard.models.*` + stdlib).

- [ ] **Step 5: Full suite + lint**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: ALL PASS, ruff clean.

- [ ] **Step 6: Commit + open PR**

```bash
git add tests/unit/test_risk_safety_properties.py tests/unit/test_risk_engine_purity.py
git commit -m "test: risk engine safety properties and purity guard (§14)"
git push -u origin phase-2
gh pr create --title "Phase 2: risk engine (pure, fully tested)" \
  --body "Implements spec §17 Phase 2 — the pure, deterministic risk engine and its policy/ceiling composition, exhaustively unit-tested before any execution path exists (§14). Models: RiskPolicy, RiskCeiling, TradeIntent, TradePlan, VettedPlan, SymbolRisk. No broker/LLM; no live verification needed."
```

---

## Out of Scope (Phase 2)

Deferred to later phases — do **not** build here:
- **Auto-adjustment of oversized intents** — `VettedPlan.adjusted` stays empty (documented forward-seam).
- **Kill-switch enforcement + high-water mark / `PerformanceTracker`** (spec §8 step 4; Phase 6). The threshold field exists; the halt does not.
- **Where `market: dict[str, SymbolRisk]` comes from** — the data layer + `SignalResolver` (Phase 3) will populate it.
- **Strategy loading / where overrides come from** — the strategy registry is a later phase; Phase 2 tests merging with synthetic override dicts.
- **The execution path, `OrderExecutor`, `ApprovalGate`** (Phase 5) — the risk engine deliberately exists before any of it.
```