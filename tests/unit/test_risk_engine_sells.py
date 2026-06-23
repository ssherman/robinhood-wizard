# tests/unit/test_risk_engine_sells.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState, Position
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.risk.engine import vet


def _market(symbol="AAPL", price="100"):
    return {
        symbol: SymbolRisk(
            symbol=symbol,
            price=Decimal(price),
            average_volume=Decimal("50000000"),
            market_cap=Decimal("3000000000000"),
        )
    }


def _portfolio_with_holding(qty="10"):
    held = Position(
        symbol="AAPL",
        quantity=qty,
        average_cost="100",
        cost_basis=str(Decimal(qty) * Decimal("100")),
        market_value=str(Decimal(qty) * Decimal("100")),
    )
    return PortfolioState(
        account_number="ACC1",
        positions=[held],
        cash=Decimal("0"),
        buying_power=Decimal("0"),
        total_value=str(Decimal(qty) * Decimal("100")),
    )


def test_sell_within_holding_is_approved():
    plan = TradePlan(
        intents=[TradeIntent(side="sell", symbol="AAPL", quantity="5", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(), _market())
    assert [i.symbol for i in result.approved] == ["AAPL"]


def test_sell_more_than_held_rejected():
    plan = TradePlan(
        intents=[TradeIntent(side="sell", symbol="AAPL", quantity="20", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(qty="10"), _market())
    assert "held" in result.rejected[0].reason.lower()


def test_sell_exempt_from_cash_reserve_and_deploy():
    # No cash, reserve 10% — a sell must still be allowed (it raises cash, not spends it).
    plan = TradePlan(
        intents=[TradeIntent(side="sell", symbol="AAPL", quantity="10", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(qty="10"), _market())
    assert len(result.approved) == 1
    assert result.rejected == []


def test_sell_still_subject_to_slippage():
    plan = TradePlan(
        intents=[
            TradeIntent(side="sell", symbol="AAPL", quantity="5", limit_price="90")  # 10% off
        ]
    )
    result = vet(plan, RiskPolicy(), _portfolio_with_holding(), _market())
    assert "slippage" in result.rejected[0].reason.lower()


def test_sell_frees_cash_for_a_following_buy():
    # Hold 10 AAPL ($1000), no cash. Sell 10 (frees ~$1000), then buy MSFT $500.
    # Without the freed cash the buy would breach the reserve.
    policy = RiskPolicy(
        cash_reserve_pct="0", max_deploy_pct_per_cycle="100", max_position_pct="100"
    )
    market = {**_market("AAPL"), **_market("MSFT")}
    intents = [
        TradeIntent(side="sell", symbol="AAPL", quantity="10", limit_price="100"),
        TradeIntent(side="buy", symbol="MSFT", quantity="5", limit_price="100"),
    ]
    result = vet(TradePlan(intents=intents), policy, _portfolio_with_holding(qty="10"), market)
    assert {i.symbol for i in result.approved} == {"AAPL", "MSFT"}
    assert result.rejected == []
