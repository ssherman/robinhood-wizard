# Bucketed Allocation — Deploy-Completeness + Rationale Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the bucketed path, surface each position's `thesis` as its trade rationale and deploy a strategy closer to its bucket targets by (a) redistributing dollars freed by rejected/floored names to surviving names in the same bucket and (b) interleaving buy intents so a binding trade cap is shared fairly instead of starving late buckets.

**Architecture:** A bounded `allocate ↔ vet` loop (`core/deploy.py::complete_allocation`) feeds `vet`'s rejected buy symbols back to the **pure** allocator as exclusions and returns the **best-deploying round** (provably never worse than round 0). The allocator emits buys round-robin by within-bucket rank so the cap is fair; `vet` is untouched and stays the sole cap authority. A pure enricher fills per-bucket deployed/cash-left and explanatory notes for render.

**Tech Stack:** Python 3.12, pydantic v2 (Decimal money), pytest (`uv run pytest`), ruff (line-length 100). Tests are TDD: failing test first, minimal impl, green, commit.

## Global Constraints

- **`allocate()` stays pure** — no imports of `rh_wizard.{broker,auth,memory,cli,llm}`; guarded by `tests/unit/test_allocator_purity.py`. Deterministic.
- **`vet()` is the sole, un-bypassable cap authority** — no rejection/cap logic is added or relocated anywhere else. `risk/engine.py` is **not modified** by this plan.
- **Flat (non-bucketed) path stays byte-for-byte unchanged** — every new allocator parameter defaults to the value that reproduces today's behavior.
- **Cycle stays brain-agnostic** — `core/` imports no `openai`/`strands`/`llm`.
- **DryRun stays default**; the Phase 5 execute path (`test_human_approval_places_orders_from_bucketed_path`) must stay green — it consumes only the final `VettedPlan`.
- **Determinism** — no `Date.now`/randomness; identical inputs → identical converged plan.
- **Money/quantities are `Decimal`.** Lines ≤ 100 chars; imports sorted (ruff `I`).
- **Run a single test:** `uv run pytest tests/unit/<file>::<test> -v`. **Lint:** `uv run ruff check src tests`.

---

## File structure

| File | Responsibility | Tasks |
|------|----------------|-------|
| `src/rh_wizard/allocation/engine.py` | Pure sizing: rationale passthrough, `exclude` param, rank-interleave, public `bucket_membership`. | 1, 2, 3 |
| `src/rh_wizard/models/allocation.py` | `BucketAllocation` gains `budget`/`deployed`/`cash_left`. | 4 |
| `src/rh_wizard/core/deploy.py` *(new)* | `complete_allocation` loop + `deployment_summary` enricher. Pure; composes `allocate` + `vet`. | 5, 6 |
| `src/rh_wizard/core/cycle.py` | `_run_bucketed` calls `complete_allocation`. | 7 |
| `src/rh_wizard/cli/render.py` | Deployed column + render `allocation.notes`. | 8 |
| `tests/unit/test_allocator.py` | Rationale, exclude, interleave, membership. | 1, 2, 3 |
| `tests/unit/test_models_allocation.py` | New model fields. | 4 |
| `tests/unit/test_deploy.py` *(new)* | Loop: redistribution, never-worse, fairness, determinism, notes. | 5, 6 |
| `tests/unit/test_cycle.py` | Integration: deployed + rationale reported; regressions. | 7 |
| `tests/unit/test_render_cycle.py` | Render Deployed + notes. | 8 |

---

## Task 1: Rationale passthrough (bucketed buys + sells)

**Files:**
- Modify: `src/rh_wizard/allocation/engine.py` (`_buy_intent`, `_split_buys`, `_trim_sells`)
- Test: `tests/unit/test_allocator.py`

**Interfaces:**
- Consumes: `RecommendedPosition.thesis` (`models/allocation.py:24`), `TradeIntent.rationale` (`models/plan.py:21`).
- Produces: bucketed buy `TradeIntent`s carry `pos.thesis`; trim sells carry `"trim to bucket target"`. No sizing change.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_allocator.py` (helpers `_strategy`, `_market`, `_portfolio`, `Position` already exist in the file):

```python
def test_bucketed_buy_carries_position_thesis():
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA", weight="1", thesis="memory upcycle")
                ],
            )
        ]
    )
    plan, _ = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), _market({"NVDA": "100"}))
    assert plan.intents[0].rationale == "memory upcycle"


def test_bucketed_trim_sell_carries_fixed_rationale():
    held = [
        Position(
            symbol="NVDA", quantity="9", average_cost="100", cost_basis="900", market_value="900"
        )
    ]
    strat = _strategy([Bucket(id="ai", target_pct="10")], rebalance_mode="full")
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    plan, _ = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="1000", positions=held), _market({"NVDA": "100"})
    )
    sells = [i for i in plan.intents if i.side == "sell"]
    assert sells and all(i.rationale == "trim to bucket target" for i in sells)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_allocator.py::test_bucketed_buy_carries_position_thesis tests/unit/test_allocator.py::test_bucketed_trim_sell_carries_fixed_rationale -v`
Expected: FAIL — rationale is `""`, not the thesis / fixed string.

- [ ] **Step 3: Implement — thread thesis into buys, fixed string into sells**

In `src/rh_wizard/allocation/engine.py`, replace `_buy_intent` (currently lines ~66-78) with:

```python
def _buy_intent(
    symbol: str,
    dollars: Decimal,
    data: SymbolData,
    allow_fractional: bool,
    rationale: str = "",
) -> TradeIntent | None:
    price = data.price
    if price is None or price <= 0 or dollars <= 0:
        return None
    fractional = allow_fractional and bool(data.fractionable)
    if fractional:
        return TradeIntent(
            side=_BUY, symbol=symbol, amount=dollars, limit_price=price, rationale=rationale
        )
    qty = (dollars / price).to_integral_value(rounding=ROUND_DOWN)
    if qty <= 0:
        return None
    return TradeIntent(
        side=_BUY, symbol=symbol, quantity=qty, limit_price=price, rationale=rationale
    )
```

In `_split_buys`, change the `_buy_intent(...)` call (currently line ~111) to pass the thesis:

```python
        intent = _buy_intent(sym, dollars, market[sym], allow_fractional, rationale=pos.thesis)
```

In `_trim_sells`, change the sell construction (currently line ~145) to:

```python
        intents.append(
            TradeIntent(
                side=_SELL,
                symbol=sym,
                quantity=qty,
                limit_price=data.price,
                rationale="trim to bucket target",
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_allocator.py -q`
Expected: PASS (all allocator tests, incl. the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/allocation/engine.py tests/unit/test_allocator.py
git commit -m "feat(alloc): pass bucket position thesis through as trade rationale"
```

---

## Task 2: `exclude` parameter on `allocate()`

**Files:**
- Modify: `src/rh_wizard/allocation/engine.py` (`allocate`, `_split_buys`)
- Test: `tests/unit/test_allocator.py`

**Interfaces:**
- Produces: `allocate(strategy, recommendation, policy, portfolio, market, exclude: frozenset[str] = frozenset())`. With empty `exclude` (default), behavior is byte-for-byte unchanged. Excluded symbols are dropped from their bucket's split; their dollars flow to survivors via the existing weight normalization.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_allocator.py`:

```python
def test_exclude_drops_name_and_redistributes_to_survivors():
    # investable 900, single bucket 100%. Without exclude: NVDA 600 / MSFT 300.
    # Excluding NVDA hands its whole share to MSFT -> MSFT gets the full 900.
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA", weight="2"),
                    RecommendedPosition(symbol="MSFT", weight="1"),
                ],
            )
        ]
    )
    market = _market({"NVDA": "100", "MSFT": "200"})
    plan, _ = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="1000"), market, exclude=frozenset({"NVDA"})
    )
    by = {i.symbol: i for i in plan.intents}
    assert "NVDA" not in by
    assert by["MSFT"].amount == Decimal("900")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_allocator.py::test_exclude_drops_name_and_redistributes_to_survivors -v`
Expected: FAIL — `allocate()` has no `exclude` parameter (`TypeError`).

- [ ] **Step 3: Implement — add `exclude` and thread it to `_split_buys`**

In `src/rh_wizard/allocation/engine.py`, change the `allocate` signature to add a final parameter:

```python
def allocate(
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: dict[str, SymbolData],
    exclude: frozenset[str] = frozenset(),
) -> tuple[TradePlan, AllocationReport]:
```

In `allocate`, pass `exclude` into the `_split_buys(...)` call (currently lines ~178-185):

```python
            buys = _split_buys(
                rec_by_bucket.get(bucket.id),
                budget - current,
                market,
                strategy.allow_fractional,
                member,
                bucket.id,
                exclude,
            )
```

Add the `exclude` parameter to `_split_buys` and filter on it. Change its signature and the `priced` comprehension:

```python
def _split_buys(
    rec: BucketRecommendation | None,
    shortfall: Decimal,
    market: dict[str, SymbolData],
    allow_fractional: bool,
    member: dict[str, str],
    bucket_id: str,
    exclude: frozenset[str],
) -> list[TradeIntent]:
    if rec is None or shortfall <= 0:
        return []
    priced = [
        p
        for p in rec.positions
        if _norm(p.symbol) in market
        and market[_norm(p.symbol)].price
        and member.get(_norm(p.symbol)) == bucket_id
        and _norm(p.symbol) not in exclude
    ]
```

(Leave the rest of `_split_buys` unchanged for now — Task 3 adds the rank sort.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_allocator.py -q`
Expected: PASS (new test plus all existing — the default `frozenset()` preserves current behavior).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/allocation/engine.py tests/unit/test_allocator.py
git commit -m "feat(alloc): add exclude param to allocate() for within-bucket redistribution"
```

---

## Task 3: Fair interleaving + public `bucket_membership`

**Files:**
- Modify: `src/rh_wizard/allocation/engine.py` (rename `_membership`→`bucket_membership`, rank-sort in `_split_buys`, interleave in `allocate`, new `_interleave`)
- Test: `tests/unit/test_allocator.py`

**Interfaces:**
- Produces: `bucket_membership(strategy, recommendation) -> dict[str, str]` (public, pure — symbol→bucket_id). `allocate` returns buy intents **interleaved round-robin by within-bucket rank** (rank = weight desc, then symbol asc). Sells still precede buys.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_allocator.py`:

```python
def test_buys_interleaved_round_robin_by_rank_across_buckets():
    strat = _strategy(
        [Bucket(id="a", target_pct="50"), Bucket(id="b", target_pct="50")]
    )
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="a",
                positions=[
                    RecommendedPosition(symbol="A1", weight="2"),
                    RecommendedPosition(symbol="A2", weight="1"),
                ],
            ),
            BucketRecommendation(
                bucket_id="b",
                positions=[
                    RecommendedPosition(symbol="B1", weight="2"),
                    RecommendedPosition(symbol="B2", weight="1"),
                ],
            ),
        ]
    )
    market = _market({"A1": "100", "A2": "100", "B1": "100", "B2": "100"})
    plan, _ = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), market)
    order = [i.symbol for i in plan.intents if i.side == "buy"]
    assert order == ["A1", "B1", "A2", "B2"]


def test_bucket_membership_maps_symbols_to_buckets():
    from rh_wizard.allocation.engine import bucket_membership

    strat = _strategy([Bucket(id="a", target_pct="100", universe=["HELD"])])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="a", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    member = bucket_membership(strat, rec)
    assert member["NVDA"] == "a"
    assert member["HELD"] == "a"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_allocator.py::test_buys_interleaved_round_robin_by_rank_across_buckets tests/unit/test_allocator.py::test_bucket_membership_maps_symbols_to_buckets -v`
Expected: FAIL — buys are bucket-sequential (`["A1","A2","B1","B2"]`); `bucket_membership` does not exist (`ImportError`).

- [ ] **Step 3a: Rename `_membership` → `bucket_membership`**

In `src/rh_wizard/allocation/engine.py`, rename the function `def _membership(` to `def bucket_membership(`, and update its one call site inside `allocate` (currently line ~159) from `member = _membership(strategy, recommendation)` to:

```python
    member = bucket_membership(strategy, recommendation)
```

- [ ] **Step 3b: Add the rank sort to `_split_buys`**

Replace the body of `_split_buys` from the `weights = [...]` line through `return intents` with (this is the full tail of the function — the signature/`priced` filter from Task 2 stays):

```python
    weights = [
        p.weight if (p.weight is not None and p.weight > 0) else Decimal("0") for p in priced
    ]
    total = sum(weights)
    if total <= 0:  # equal-weight fallback
        weights = [Decimal("1") for _ in priced]
        total = Decimal(len(priced))
    # Rank by weight desc, then symbol asc, so allocate() can interleave buckets fairly by rank.
    ranked = sorted(
        zip(priced, weights, strict=True), key=lambda pw: (-pw[1], _norm(pw[0].symbol))
    )
    intents: list[TradeIntent] = []
    for pos, w in ranked:
        sym = _norm(pos.symbol)
        dollars = shortfall * w / total
        intent = _buy_intent(sym, dollars, market[sym], allow_fractional, rationale=pos.thesis)
        if intent is not None:
            intents.append(intent)
    return intents
```

- [ ] **Step 3c: Add `_interleave` and use it in `allocate`**

Add this helper to `src/rh_wizard/allocation/engine.py` (e.g. just above `allocate`):

```python
def _interleave(bucket_buys: list[list[TradeIntent]]) -> list[TradeIntent]:
    """Round-robin across buckets by rank so a binding cap is shared fairly, not consumed
    bucket-by-bucket (which starves late buckets). Each inner list is one bucket's buys,
    already ordered by rank (weight desc, symbol asc)."""
    out: list[TradeIntent] = []
    if not bucket_buys:
        return out
    depth = max(len(b) for b in bucket_buys)
    for rank in range(depth):
        for buys in bucket_buys:
            if rank < len(buys):
                out.append(buys[rank])
    return out
```

In `allocate`, change the buy accumulator and the underweight branch. Replace the initializer (currently `buy_intents: list[TradeIntent] = []`, line ~162) with:

```python
    bucket_buys: list[list[TradeIntent]] = []
```

In the underweight (`elif drift < 0:`) branch, replace `if buys: buy_intents.extend(buys); action = "buy"` (currently lines ~186-190) with:

```python
            if buys:
                bucket_buys.append(buys)
                action = "buy"
            else:
                action = "no candidates"
```

Finally, just before the `orphans = ...` line (currently ~220), build the interleaved buy list:

```python
    buy_intents = _interleave(bucket_buys)
```

(The closing `return TradePlan(intents=sell_intents + buy_intents, ...)` already references `buy_intents` and is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_allocator.py -q && uv run pytest tests/unit/test_allocator_purity.py -q`
Expected: PASS — including the purity guard (no new forbidden imports).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/allocation/engine.py tests/unit/test_allocator.py
git commit -m "feat(alloc): interleave buys by rank across buckets; expose bucket_membership"
```

---

## Task 4: `BucketAllocation` deploy-reporting fields

**Files:**
- Modify: `src/rh_wizard/models/allocation.py` (`BucketAllocation`)
- Test: `tests/unit/test_models_allocation.py`

**Interfaces:**
- Produces: `BucketAllocation` gains `budget: Decimal = 0`, `deployed: Decimal = 0`, `cash_left: Decimal = 0`. Existing construction sites keep working (defaults).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_models_allocation.py` (it already imports from `rh_wizard.models.allocation`; add `BucketAllocation` and `from decimal import Decimal` if not present):

```python
def test_bucket_allocation_has_deploy_fields():
    b = BucketAllocation(
        bucket_id="ai",
        target_pct=Decimal("35"),
        current_pct=Decimal("0"),
        drift_pct=Decimal("-35"),
        within_band=False,
        action="buy",
        budget=Decimal("1050"),
        deployed=Decimal("900"),
        cash_left=Decimal("150"),
    )
    assert b.budget == Decimal("1050")
    assert b.deployed == Decimal("900")
    assert b.cash_left == Decimal("150")


def test_bucket_allocation_deploy_fields_default_zero():
    b = BucketAllocation(
        bucket_id="ai",
        target_pct=Decimal("35"),
        current_pct=Decimal("0"),
        drift_pct=Decimal("-35"),
        within_band=False,
        action="buy",
    )
    assert b.budget == Decimal("0")
    assert b.deployed == Decimal("0")
    assert b.cash_left == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models_allocation.py -k bucket_allocation -v`
Expected: FAIL — unknown fields `budget`/`deployed`/`cash_left`.

- [ ] **Step 3: Implement — add the three fields**

In `src/rh_wizard/models/allocation.py`, in `class BucketAllocation`, add after `action: str`:

```python
    budget: Decimal = Decimal("0")  # target dollars for this bucket (target_pct × investable)
    deployed: Decimal = Decimal("0")  # approved-buy dollars mapped to this bucket
    cash_left: Decimal = Decimal("0")  # budget − deployed, floored at 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models_allocation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/models/allocation.py tests/unit/test_models_allocation.py
git commit -m "feat(models): add budget/deployed/cash_left to BucketAllocation"
```

---

## Task 5: `complete_allocation` loop (redistribution + keep-best)

**Files:**
- Create: `src/rh_wizard/core/deploy.py`
- Test (create): `tests/unit/test_deploy.py`

**Interfaces:**
- Consumes: `allocate(..., exclude=...)` (Task 2/3), `vet` (`risk/engine.py`), `MarketContext.symbols` / `.to_symbol_risk()`.
- Produces: `complete_allocation(strategy, recommendation, policy, portfolio, market, max_rounds=3) -> tuple[TradePlan, AllocationReport, VettedPlan]`. Runs the bounded allocate↔vet loop, excludes all rejected buy symbols each round, and returns the round with the **largest total approved-buy dollars** (round 0 always a candidate; ties → earliest round). *This task returns the allocate report unmodified; Task 6 enriches it.*

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_deploy.py`:

```python
from decimal import Decimal

from rh_wizard.allocation.engine import bucket_membership
from rh_wizard.core.deploy import complete_allocation
from rh_wizard.models.allocation import (
    AllocationRecommendation,
    BucketRecommendation,
    RecommendedPosition,
)
from rh_wizard.models.bucket import Bucket
from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.models.strategy import Strategy


def _sym(symbol, price):
    return SymbolData(
        symbol=symbol,
        price=Decimal(price),
        average_volume=Decimal("5000000"),
        market_cap=Decimal("5000000000"),
        fractionable=True,
    )


def _ctx(*syms):
    return MarketContext(symbols={s.symbol: s for s in syms})


def _portfolio(cash="1000"):
    return PortfolioState(
        account_number="ACC1",
        positions=[],
        cash=Decimal(cash),
        buying_power=Decimal(cash),
        total_value=Decimal(cash),
    )


def _policy(**kw):
    base = dict(
        max_position_pct=Decimal("100"),
        cash_reserve_pct=Decimal("0"),
        max_deploy_pct_per_cycle=Decimal("100"),
        max_trades_per_cycle=20,
        slippage_band_pct=Decimal("0.5"),
        min_price=Decimal("5"),
        min_avg_volume=Decimal("1000000"),
        min_market_cap=Decimal("1000000000"),
    )
    base.update(kw)
    return RiskPolicy(**base)


def _rec(bucket_id, *symbol_weights):
    return AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id=bucket_id,
                positions=[
                    RecommendedPosition(symbol=s, weight=w) for s, w in symbol_weights
                ],
            )
        ]
    )


def test_rejected_name_dollars_redistribute_to_survivor():
    # BAD (price 3 < min_price 5) is rejected; its half of the budget flows to GOOD.
    strat = Strategy(id="s", name="S", buckets=[Bucket(id="ai", target_pct="100")])
    rec = _rec("ai", ("GOOD", "1"), ("BAD", "1"))
    market = _ctx(_sym("GOOD", "100"), _sym("BAD", "3"))
    _, _, vetted = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    approved = {i.symbol: i for i in vetted.approved}
    assert "BAD" not in approved
    assert approved["GOOD"].amount == Decimal("1000")


def test_redistribution_never_deploys_less_than_round_zero():
    # Budget 600, 3 equal names, position cap 200/name. Round 0: AAA+BBB approved (400),
    # CCC rejected (price 3). Excluding CCC would push AAA/BBB to 300 each -> both breach the
    # 200 cap -> deployed 0. keep-best must return round 0 (400).
    strat = Strategy(id="s", name="S", buckets=[Bucket(id="ai", target_pct="60")])
    rec = _rec("ai", ("AAA", "1"), ("BBB", "1"), ("CCC", "1"))
    market = _ctx(_sym("AAA", "100"), _sym("BBB", "100"), _sym("CCC", "3"))
    _, _, vetted = complete_allocation(
        strat, rec, _policy(max_position_pct=Decimal("20")), _portfolio("1000"), market
    )
    deployed = sum((i.amount or Decimal("0")) for i in vetted.approved if i.side == "buy")
    assert deployed == Decimal("400")
    assert {i.symbol for i in vetted.approved} == {"AAA", "BBB"}


def test_interleaving_prevents_late_bucket_starvation_under_trade_cap():
    # 3 buckets x 3 names, cap = 3 trades. Interleaving gives each bucket its rank-1 name in
    # the first 3 slots; redistribution then fills each bucket from its single survivor.
    buckets = [
        Bucket(id="a", target_pct="30"),
        Bucket(id="b", target_pct="30"),
        Bucket(id="c", target_pct="30"),
    ]
    strat = Strategy(id="s", name="S", buckets=buckets)

    def names(prefix):
        return [RecommendedPosition(symbol=f"{prefix}{n}", weight="1") for n in (1, 2, 3)]

    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="a", positions=names("A")),
            BucketRecommendation(bucket_id="b", positions=names("B")),
            BucketRecommendation(bucket_id="c", positions=names("C")),
        ]
    )
    market = _ctx(*[_sym(f"{p}{n}", "100") for p in "ABC" for n in (1, 2, 3)])
    _, _, vetted = complete_allocation(
        strat, rec, _policy(max_trades_per_cycle=3), _portfolio("1000"), market
    )
    member = bucket_membership(strat, rec)
    approved_buckets = {member[i.symbol] for i in vetted.approved if i.side == "buy"}
    assert approved_buckets == {"a", "b", "c"}


def test_complete_allocation_is_deterministic():
    strat = Strategy(id="s", name="S", buckets=[Bucket(id="ai", target_pct="100")])
    rec = _rec("ai", ("GOOD", "2"), ("ALSO", "1"), ("BAD", "1"))
    market = _ctx(_sym("GOOD", "100"), _sym("ALSO", "100"), _sym("BAD", "3"))
    _, _, a = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    _, _, b = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    assert [(i.symbol, i.amount) for i in a.approved] == [(i.symbol, i.amount) for i in b.approved]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_deploy.py -v`
Expected: FAIL — `rh_wizard.core.deploy` does not exist (`ImportError`).

- [ ] **Step 3: Implement the loop**

Create `src/rh_wizard/core/deploy.py`:

```python
"""Deploy-completeness for bucketed allocation (spec docs/.../2026-06-28-bucket-deploy-completeness).

``complete_allocation`` runs a bounded allocate <-> vet loop: it feeds vet's rejected buy symbols
back to the pure allocator as exclusions, so dollars freed by a rejected/floored name flow to the
surviving names in the same bucket. It returns the best-deploying round (never worse than round 0).
``vet`` stays the sole cap authority; ``allocate`` stays pure. This module composes them and is
itself pure and deterministic (no I/O, no llm).
"""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.allocation.engine import allocate
from rh_wizard.models.allocation import AllocationRecommendation, AllocationReport
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradeIntent, TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.models.strategy import Strategy
from rh_wizard.risk.engine import vet

_BUY = "buy"
_MAX_ROUNDS = 3


def _order_value(intent: TradeIntent) -> Decimal:
    if intent.amount is not None:
        return intent.amount
    if intent.quantity is not None and intent.limit_price is not None:
        return intent.quantity * intent.limit_price
    return Decimal("0")


def _deployed(vetted: VettedPlan) -> Decimal:
    return sum((_order_value(i) for i in vetted.approved if i.side == _BUY), Decimal("0"))


def complete_allocation(
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: MarketContext,
    max_rounds: int = _MAX_ROUNDS,
) -> tuple[TradePlan, AllocationReport, VettedPlan]:
    symbols = market.symbols
    risk = market.to_symbol_risk()
    excluded: set[str] = set()

    plan, report = allocate(strategy, recommendation, policy, portfolio, symbols)
    vetted = vet(plan, policy, portfolio, risk)
    best = (plan, report, vetted, _deployed(vetted))

    for _ in range(max_rounds):
        newly = {r.intent.symbol for r in vetted.rejected if r.intent.side == _BUY} - excluded
        if not newly:
            break
        excluded |= newly
        plan, report = allocate(
            strategy, recommendation, policy, portfolio, symbols, exclude=frozenset(excluded)
        )
        vetted = vet(plan, policy, portfolio, risk)
        deployed = _deployed(vetted)
        if deployed > best[3]:
            best = (plan, report, vetted, deployed)

    plan, report, vetted, _ = best
    return plan, report, vetted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_deploy.py -q`
Expected: PASS (all five).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/core/deploy.py tests/unit/test_deploy.py
git commit -m "feat(deploy): bounded allocate<->vet redistribution loop (keep-best round)"
```

---

## Task 6: `deployment_summary` enrichment (deployed/cash-left + notes)

**Files:**
- Modify: `src/rh_wizard/core/deploy.py` (add `deployment_summary`, `_dominant`, `_norm`; wire into `complete_allocation`)
- Test: `tests/unit/test_deploy.py`

**Interfaces:**
- Produces: `deployment_summary(report, strategy, recommendation, vetted) -> AllocationReport` — fills each `BucketAllocation`'s `budget`/`deployed`/`cash_left` (budget = `target_pct/100 × report.investable`) and appends one note per under-deployed bucket that had rejected buys, naming the dominant rejection reason. `complete_allocation` now returns the enriched report.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_deploy.py`:

```python
def test_zero_survivor_bucket_left_as_cash_with_reason_note():
    strat = Strategy(
        id="s", name="S", buckets=[Bucket(id="weed", name="Cannabis", target_pct="100")]
    )
    rec = _rec("weed", ("BAD", "1"))  # price 3 < min_price 5 -> rejected, no survivor
    market = _ctx(_sym("BAD", "3"))
    _, report, _ = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    b = report.buckets[0]
    assert b.budget == Decimal("1000")
    assert b.deployed == Decimal("0")
    assert b.cash_left == Decimal("1000")
    assert any(
        "Cannabis" in n and "left as cash" in n and "liquidity floor" in n for n in report.notes
    )


def test_successful_redistribution_reports_full_deploy_no_note():
    strat = Strategy(id="s", name="S", buckets=[Bucket(id="ai", name="AI", target_pct="100")])
    rec = _rec("ai", ("GOOD", "1"), ("BAD", "1"))
    market = _ctx(_sym("GOOD", "100"), _sym("BAD", "3"))
    _, report, _ = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    b = report.buckets[0]
    assert b.deployed == Decimal("1000")
    assert b.cash_left == Decimal("0")
    assert report.notes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_deploy.py -k "zero_survivor or successful_redistribution" -v`
Expected: FAIL — `report.buckets[0].budget`/`deployed` are still `0` and `report.notes` is empty (no enrichment yet).

- [ ] **Step 3: Implement the enricher and wire it in**

In `src/rh_wizard/core/deploy.py`, change the `allocate` import line to also import `bucket_membership`:

```python
from rh_wizard.allocation.engine import allocate, bucket_membership
```

Add these helpers (e.g. below `_deployed`):

```python
def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _dominant(reasons: list[str]) -> str:
    counts: dict[str, int] = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    # Most frequent reason; ties broken alphabetically for determinism.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def deployment_summary(
    report: AllocationReport,
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    vetted: VettedPlan,
) -> AllocationReport:
    member = bucket_membership(strategy, recommendation)
    investable = report.investable
    deployed_by_bucket: dict[str, Decimal] = {}
    for i in vetted.approved:
        if i.side != _BUY:
            continue
        b = member.get(_norm(i.symbol))
        if b is not None:
            deployed_by_bucket[b] = deployed_by_bucket.get(b, Decimal("0")) + _order_value(i)
    rejected_by_bucket: dict[str, list[str]] = {}
    for r in vetted.rejected:
        if r.intent.side != _BUY:
            continue
        b = member.get(_norm(r.intent.symbol))
        if b is not None:
            rejected_by_bucket.setdefault(b, []).append(r.reason)

    new_buckets = []
    notes = list(report.notes)
    for b in report.buckets:
        budget = (b.target_pct / 100 * investable) if investable > 0 else Decimal("0")
        deployed = deployed_by_bucket.get(b.bucket_id, Decimal("0"))
        cash_left = budget - deployed
        if cash_left < 0:
            cash_left = Decimal("0")
        new_buckets.append(
            b.model_copy(update={"budget": budget, "deployed": deployed, "cash_left": cash_left})
        )
        reasons = rejected_by_bucket.get(b.bucket_id, [])
        if cash_left > 0 and reasons:
            label = b.name or b.bucket_id
            notes.append(
                f"{label}: ${cash_left:.2f} left as cash — "
                f"{len(reasons)} name(s) rejected ({_dominant(reasons)})"
            )
    return report.model_copy(update={"buckets": new_buckets, "notes": notes})
```

In `complete_allocation`, replace the final two lines (`plan, report, vetted, _ = best` / `return plan, report, vetted`) with:

```python
    plan, report, vetted, _ = best
    report = deployment_summary(report, strategy, recommendation, vetted)
    return plan, report, vetted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_deploy.py -q`
Expected: PASS (all of Task 5 + Task 6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/core/deploy.py tests/unit/test_deploy.py
git commit -m "feat(deploy): enrich report with per-bucket deployed/cash-left + reason notes"
```

---

## Task 7: Wire `_run_bucketed` to `complete_allocation`

**Files:**
- Modify: `src/rh_wizard/core/cycle.py` (`_run_bucketed`, imports)
- Test: `tests/unit/test_cycle.py`

**Interfaces:**
- Consumes: `complete_allocation(strategy, recommendation, policy, portfolio, market) -> (TradePlan, AllocationReport, VettedPlan)`.
- Produces: the bucketed cycle's `result.allocation` now carries per-bucket `deployed`/`cash_left`; approved bucket intents carry their thesis. Downstream journal/execute/render unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_cycle.py` (add `from decimal import Decimal` at the top of the file if absent):

```python
def test_bucketed_cycle_reports_deployment_and_rationale():
    from rh_wizard.models.allocation import (
        AllocationRecommendation,
        BucketRecommendation,
        RecommendedPosition,
    )
    from rh_wizard.models.bucket import Bucket

    strategy = Strategy(
        id="b",
        name="B",
        signals_needed={Signal.PRICE},
        risk_overrides={"max_position_pct": "100", "max_deploy_pct_per_cycle": "100"},
        buckets=[Bucket(id="ai", target_pct="100", universe=["AAPL"])],
    )

    class Rec:
        def recommend(self, strategy, bucket_candidates, market, portfolio):
            return AllocationRecommendation(
                buckets=[
                    BucketRecommendation(
                        bucket_id="ai",
                        positions=[
                            RecommendedPosition(symbol="AAPL", weight="1", thesis="cheap and good")
                        ],
                    )
                ],
                summary="ok",
            )

    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.recommender = Rec()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        ai = result.allocation.buckets[0]
        assert ai.budget == Decimal("9000")  # investable 10000*0.9, target 100%
        assert ai.deployed == Decimal("9000")
        assert ai.cash_left == Decimal("0")
        assert any(
            i.symbol == "AAPL" and i.rationale == "cheap and good" for i in result.vetted.approved
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cycle.py::test_bucketed_cycle_reports_deployment_and_rationale -v`
Expected: FAIL — `ai.deployed`/`budget` are `0` (cycle still calls bare `allocate` + `vet`, no enrichment).

- [ ] **Step 3: Implement the wiring**

In `src/rh_wizard/core/cycle.py`, remove the now-unused allocate import (line ~16) `from rh_wizard.allocation.engine import allocate` and add:

```python
from rh_wizard.core.deploy import complete_allocation
```

(Keep `from rh_wizard.risk.engine import vet` — the flat path still uses it.)

In `_run_bucketed`, replace the two lines (currently ~254-255):

```python
        plan, allocation = allocate(strategy, recommendation, policy, portfolio, market.symbols)
        vetted = vet(plan, policy, portfolio, market.to_symbol_risk())
```

with:

```python
        plan, allocation, vetted = complete_allocation(
            strategy, recommendation, policy, portfolio, market
        )
```

- [ ] **Step 4: Run tests to verify they pass (incl. regressions)**

Run: `uv run pytest tests/unit/test_cycle.py -q`
Expected: PASS — the new test, plus existing `test_bucketed_cycle_completes_allocates_and_journals`, `test_flat_cycle_unchanged_has_no_allocation`, and `test_human_approval_places_orders_from_bucketed_path` all stay green.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/core/cycle.py tests/unit/test_cycle.py
git commit -m "feat(cycle): bucketed path deploys via complete_allocation loop"
```

---

## Task 8: Render Deployed column + allocation notes

**Files:**
- Modify: `src/rh_wizard/cli/render.py` (allocation table + notes; add `Decimal` import)
- Test: `tests/unit/test_render_cycle.py`

**Interfaces:**
- Consumes: `BucketAllocation.budget/deployed/cash_left` (Task 4), `AllocationReport.notes` (Task 6).
- Produces: allocation table gains a right-justified **Deployed** column (`$deployed (pct%)`, plus a `\n$cash_left left` line when `cash_left > 0`); `allocation.notes` render as `Allocation note: ...` lines.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_render_cycle.py`:

```python
def test_render_shows_deployed_and_cash_left_and_notes():
    from decimal import Decimal

    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.core.cycle import CycleResult
    from rh_wizard.models.allocation import AllocationReport, BucketAllocation
    from rh_wizard.models.cycle import CycleRun
    from rh_wizard.models.plan import VettedPlan

    run = CycleRun(run_id="r1", strategy_id="b", mode="dryrun", started_at="t", status="completed")
    result = CycleResult(
        run=run,
        vetted=VettedPlan(),
        allocation=AllocationReport(
            buckets=[
                BucketAllocation(
                    bucket_id="weed",
                    name="Cannabis",
                    target_pct=Decimal("10"),
                    current_pct=Decimal("0"),
                    drift_pct=Decimal("-10"),
                    within_band=False,
                    action="no candidates",
                    budget=Decimal("300"),
                    deployed=Decimal("0"),
                    cash_left=Decimal("300"),
                )
            ],
            investable=Decimal("3000"),
            notes=["Cannabis: $300.00 left as cash — 5 name(s) rejected (max trades)"],
        ),
    )
    out = render_cycle_result(result)
    assert "Deployed" in out  # new column header
    assert "left as cash" in out  # note rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render_cycle.py::test_render_shows_deployed_and_cash_left_and_notes -v`
Expected: FAIL — no "Deployed" column; notes not rendered.

- [ ] **Step 3: Implement the render changes**

In `src/rh_wizard/cli/render.py`, add the `Decimal` import near the top (after `from __future__ import annotations`):

```python
from decimal import Decimal
```

In `render_cycle_result`, in the `if allocation is not None:` block, add a Deployed column after the `table.add_column("Action")` line:

```python
        table.add_column("Deployed", justify="right")
```

Replace the `for b in allocation.buckets:` row loop (currently ~159-167) with:

```python
        for b in allocation.buckets:
            pct = (b.deployed / b.budget * 100) if b.budget > 0 else Decimal("0")
            deployed_cell = f"{fmt_money(b.deployed)} ({fmt_pct(pct)})"
            if b.cash_left > 0:
                deployed_cell += f"\n{fmt_money(b.cash_left)} left"
            table.add_row(
                b.name or b.bucket_id,
                fmt_pct(b.target_pct),
                fmt_pct(b.current_pct),
                fmt_pct(b.drift_pct),
                "yes" if b.within_band else "no",
                b.action,
                deployed_cell,
            )
```

Immediately after `lines.append(render_to_str(table).rstrip("\n"))` (and before the `if allocation.orphans:` line), add:

```python
        for note in allocation.notes:
            lines.append(f"Allocation note: {note}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_render_cycle.py -q`
Expected: PASS — the new test plus the existing `test_render_includes_allocation_block` (its `BucketAllocation` uses the zero defaults, so the Deployed cell renders `$0.00 (0.00%)` with no "left").

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/cli/render.py tests/unit/test_render_cycle.py
git commit -m "feat(render): show per-bucket deployed/cash-left + allocation notes"
```

---

## Task 9: Full-suite + lint verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: PASS — all tests, including the invariant guards `test_allocator_purity.py`, `test_risk_engine_purity.py`, `test_flat_cycle_unchanged_has_no_allocation`, and the Phase 5 execute path.

- [ ] **Step 2: Run the linter**

Run: `uv run ruff check src tests`
Expected: no errors (notably no `F401` unused `allocate` import left in `core/cycle.py`).

- [ ] **Step 3: Commit any lint fixes (if needed)**

```bash
git add -A
git commit -m "chore: ruff fixes for deploy-completeness"
```

(If Step 2 was already clean, skip this commit.)

---

## Self-review notes (already reconciled)

- **Spec coverage:** Goal 1 → Task 1. Fair interleaving (Q4) → Task 3. Redistribution loop + keep-best (Q1/Q2/Q5) → Tasks 2,5. Reporting (Q6) → Tasks 4,6,8. Wiring/invariants/tests (§5/§6) → Tasks 7,9. Flooring-remainder sweep & journal-persistence are explicit spec follow-ups — intentionally no task.
- **Determinism / never-worse:** covered by `test_complete_allocation_is_deterministic` and `test_redistribution_never_deploys_less_than_round_zero` (Task 5).
- **Type consistency:** `bucket_membership` (defined Task 3) is imported in Tasks 5/6; `complete_allocation` returns `(TradePlan, AllocationReport, VettedPlan)` consumed identically in Task 7; `BucketAllocation` fields (Task 4) are written by `deployment_summary` (Task 6) and read by render (Task 8).
- **No journal schema change** (no migration framework); `record_allocation` ignores the new report fields safely.
```
