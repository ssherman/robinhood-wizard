from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import RejectedIntent, TradeIntent, TradePlan, VettedPlan


def test_trade_intent_coerces_decimals():
    i = TradeIntent(side="buy", symbol="AAPL", quantity="10", limit_price="190.50")
    assert i.quantity == Decimal("10")
    assert i.limit_price == Decimal("190.50")
    assert i.amount is None


def test_trade_intent_normalizes_side_case_and_whitespace():
    # LLMs emit "BUY"/"Sell"; downstream (risk engine, journal) expects lowercase.
    assert TradeIntent(side="BUY", symbol="AAPL").side == "buy"
    assert TradeIntent(side=" Sell ", symbol="AAPL").side == "sell"


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
