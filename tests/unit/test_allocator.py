from decimal import Decimal

from rh_wizard.allocation.engine import allocate
from rh_wizard.models.allocation import (
    AllocationRecommendation,
    BucketRecommendation,
    RecommendedPosition,
)
from rh_wizard.models.bucket import Bucket
from rh_wizard.models.market import SymbolData
from rh_wizard.models.portfolio import PortfolioState, Position
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.models.strategy import Strategy


def _portfolio(cash="1000", positions=None, total=None):
    pos = positions or []
    held = sum((p.market_value if p.market_value is not None else p.cost_basis) for p in pos)
    return PortfolioState(
        account_number="ACC1",
        positions=pos,
        cash=Decimal(cash),
        buying_power=Decimal(cash),
        total_value=Decimal(total) if total is not None else Decimal(cash) + Decimal(held),
    )


def _market(prices, fractionable=True):
    return {
        sym: SymbolData(symbol=sym, price=Decimal(p), fractionable=fractionable)
        for sym, p in prices.items()
    }


def _strategy(buckets, **kw):
    return Strategy(id="t", name="T", buckets=buckets, **kw)


def test_single_bucket_buy_split_by_weight_fractional():
    # cash 1000, reserve 10% -> investable 900. AI target 100% -> budget 900.
    # weights NVDA 2 / MSFT 1 -> 600 / 300 (notional amounts, fractional).
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
    market = _market({"NVDA": "100", "MSFT": "200"}, fractionable=True)
    plan, report = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), market)
    by = {i.symbol: i for i in plan.intents}
    assert by["NVDA"].side == "buy" and by["NVDA"].amount == Decimal("600")
    assert by["MSFT"].amount == Decimal("300")
    assert all(i.quantity is None for i in plan.intents)  # fractional => notional amount
    assert all(i.limit_price == market[i.symbol].price for i in plan.intents)
    assert report.investable == Decimal("900")


def test_whole_share_buy_floors_and_leaves_remainder_cash():
    # investable 900, single name target 100% -> 900 budget, price 250, whole shares -> 3 (750).
    strat = _strategy([Bucket(id="ai", target_pct="100")], allow_fractional=False)
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    plan, _ = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), _market({"NVDA": "250"}))
    nvda = plan.intents[0]
    assert nvda.quantity == Decimal("3")  # floor(900/250)
    assert nvda.amount is None


def test_non_fractionable_symbol_forces_whole_shares():
    strat = _strategy([Bucket(id="ai", target_pct="100")], allow_fractional=True)
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="BRKA")])
        ]
    )
    market = _market({"BRKA": "250"}, fractionable=False)
    plan, _ = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), market)
    assert plan.intents[0].quantity == Decimal("3")
    assert plan.intents[0].amount is None


def test_equal_weight_fallback_when_no_weights():
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA"),
                    RecommendedPosition(symbol="MSFT"),
                ],
            )
        ]
    )
    plan, _ = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="1000"), _market({"NVDA": "100", "MSFT": "100"})
    )
    amounts = {i.symbol: i.amount for i in plan.intents}
    assert amounts == {"NVDA": Decimal("450"), "MSFT": Decimal("450")}  # 900 split evenly


def test_underweight_buys_only_the_shortfall():
    # AI target 100% of investable 900. Already hold 600 of NVDA -> shortfall 300.
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="6", average_cost="100", cost_basis="600", market_value="600"
        )
    ]
    plan, report = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="400", positions=held), _market({"NVDA": "100"})
    )
    # portfolio value 1000, reserve 100 -> investable 900; held 600 -> buy 300.
    assert plan.intents[0].amount == Decimal("300")
    assert report.buckets[0].action == "buy"


def test_bucket_within_band_is_skipped():
    # investable 900, target 50% -> 450. Hold 430 (current 47.8% of 900 -> drift ~ -2.2 < band 5).
    strat = _strategy([Bucket(id="ai", target_pct="50")], rebalance_band_pct="5")
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="43", average_cost="10", cost_basis="430", market_value="430"
        )
    ]
    plan, report = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="570", positions=held), _market({"NVDA": "10"})
    )
    assert plan.intents == []
    assert report.buckets[0].within_band is True
    assert report.buckets[0].action == "skipped (within band)"


def test_unpriced_recommended_symbol_is_skipped():
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA", weight="1"),
                    RecommendedPosition(symbol="GHOST", weight="1"),
                ],
            )
        ]
    )
    market = _market({"NVDA": "100"})  # GHOST unpriced
    plan, _ = allocate(strat, rec, RiskPolicy(), _portfolio(cash="1000"), market)
    assert [i.symbol for i in plan.intents] == ["NVDA"]


def test_duplicate_lots_are_summed_for_current_value():
    # cash 800 + two NVDA lots ($100 each) -> portfolio 1000, investable 900. AI target 100% ->
    # budget 900. Current NVDA = 100+100 = 200 (both lots summed) -> buy shortfall 700 (not 800).
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    nvda_lot = Position(
        symbol="NVDA", quantity="1", average_cost="100", cost_basis="100", market_value="100"
    )
    held = [nvda_lot, nvda_lot]
    plan, report = allocate(
        strat, rec, RiskPolicy(), _portfolio(cash="800", positions=held), _market({"NVDA": "100"})
    )
    assert plan.intents[0].amount == Decimal("700")
    assert report.buckets[0].action == "buy"


def test_orphan_holdings_reported_and_untouched():
    # TSLA is held but belongs to no bucket -> reported as an orphan, never traded.
    strat = _strategy([Bucket(id="ai", target_pct="100")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="1", average_cost="100", cost_basis="100", market_value="100"
        ),
        Position(
            symbol="TSLA", quantity="1", average_cost="100", cost_basis="100", market_value="100"
        ),
    ]
    plan, report = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="800", positions=held),
        _market({"NVDA": "100", "TSLA": "100"}),
    )
    assert "TSLA" in report.orphans
    assert all(i.symbol != "TSLA" for i in plan.intents)


def test_overweight_full_mode_trims_proportionally():
    # cash 100 + held 900 -> portfolio 1000, reserve 10% -> investable 900. AI target 50% ->
    # budget 450. Hold NVDA 600 + MSFT 300 in AI = 900 (current 100% of investable). Excess 450,
    # trimmed proportionally 2:1 -> sell $300 NVDA (3 sh), $150 MSFT (1.5 sh).
    strat = _strategy(
        [Bucket(id="ai", target_pct="50")], rebalance_mode="full", rebalance_band_pct="5"
    )
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA"),
                    RecommendedPosition(symbol="MSFT"),
                ],
            )
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="6", average_cost="100", cost_basis="600", market_value="600"
        ),
        Position(
            symbol="MSFT", quantity="3", average_cost="100", cost_basis="300", market_value="300"
        ),
    ]
    plan, report = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="100", positions=held),
        _market({"NVDA": "100", "MSFT": "100"}, fractionable=True),
    )
    sells = {i.symbol: i for i in plan.intents}
    assert all(i.side == "sell" for i in plan.intents)
    assert sells["NVDA"].quantity == Decimal("3")  # $300 / $100
    assert sells["MSFT"].quantity == Decimal("1.5")  # $150 / $100 (fractional ok)
    assert report.buckets[0].action == "sell"


def test_overweight_buy_only_does_not_sell():
    strat = _strategy(
        [Bucket(id="ai", target_pct="50")], rebalance_mode="buy_only", rebalance_band_pct="5"
    )
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="9", average_cost="100", cost_basis="900", market_value="900"
        )
    ]
    plan, report = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="0", positions=held, total="900"),
        _market({"NVDA": "100"}),
    )
    assert plan.intents == []
    assert report.buckets[0].action == "hold (overweight, buy_only)"


def test_whole_share_sell_floors():
    strat = _strategy(
        [Bucket(id="ai", target_pct="50")],
        rebalance_mode="full",
        rebalance_band_pct="5",
        allow_fractional=False,
    )
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")])
        ]
    )
    # portfolio 900, reserve 10% -> investable 810, target 50% -> budget 405; hold 900 ->
    # excess 495, price 100 -> sell floor(495/100)=4.
    held = [
        Position(
            symbol="NVDA", quantity="9", average_cost="100", cost_basis="900", market_value="900"
        )
    ]
    plan, _ = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="0", positions=held, total="900"),
        _market({"NVDA": "100"}, fractionable=False),
    )
    assert plan.intents[0].side == "sell"
    assert plan.intents[0].quantity == Decimal("4")


def test_symbol_shared_across_buckets_is_bought_once():
    # NVDA is recommended in both buckets; membership (first-match) assigns it to "a".
    # Bucket "a" buys NVDA; bucket "b" must NOT re-buy NVDA — it buys only MSFT.
    strat = _strategy([Bucket(id="a", target_pct="50"), Bucket(id="b", target_pct="50")])
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="a", positions=[RecommendedPosition(symbol="NVDA")]),
            BucketRecommendation(
                bucket_id="b",
                positions=[RecommendedPosition(symbol="NVDA"), RecommendedPosition(symbol="MSFT")],
            ),
        ]
    )
    plan, _ = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="1000"),
        _market({"NVDA": "100", "MSFT": "100"}),
    )
    nvda_buys = [i for i in plan.intents if i.symbol == "NVDA"]
    assert len(nvda_buys) == 1  # bought once (bucket a), not duplicated
    assert nvda_buys[0].amount == Decimal("450")  # investable 900, bucket a budget 450
    msft_buys = [i for i in plan.intents if i.symbol == "MSFT"]
    assert msft_buys[0].amount == Decimal("450")  # bucket b buys only MSFT (NVDA filtered out)


def test_sells_are_ordered_before_buys():
    # AI overweight (sell), energy underweight (buy). investable 900.
    strat = _strategy(
        [Bucket(id="ai", target_pct="30"), Bucket(id="energy", target_pct="30")],
        rebalance_mode="full",
        rebalance_band_pct="5",
    )
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA")]),
            BucketRecommendation(bucket_id="energy", positions=[RecommendedPosition(symbol="XOM")]),
        ]
    )
    held = [
        Position(
            symbol="NVDA", quantity="6", average_cost="100", cost_basis="600", market_value="600"
        )
    ]
    plan, _ = allocate(
        strat,
        rec,
        RiskPolicy(),
        _portfolio(cash="400", positions=held, total="1000"),
        _market({"NVDA": "100", "XOM": "100"}),
    )
    sides = [i.side for i in plan.intents]
    assert sides[0] == "sell"  # NVDA trim comes first
    assert "buy" in sides  # XOM buy after
    assert sides.index("sell") < sides.index("buy")


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
