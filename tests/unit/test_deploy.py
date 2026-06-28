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


def test_complete_allocation_is_deterministic():
    strat = Strategy(id="s", name="S", buckets=[Bucket(id="ai", target_pct="100")])
    rec = _rec("ai", ("GOOD", "2"), ("ALSO", "1"), ("BAD", "1"))
    market = _ctx(_sym("GOOD", "100"), _sym("ALSO", "100"), _sym("BAD", "3"))
    _, _, a = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    _, _, b = complete_allocation(strat, rec, _policy(), _portfolio("1000"), market)
    assert [(i.symbol, i.amount) for i in a.approved] == [(i.symbol, i.amount) for i in b.approved]
