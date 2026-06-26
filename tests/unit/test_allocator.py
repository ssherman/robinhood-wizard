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
    held = sum((p.market_value or p.cost_basis) for p in pos)
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
