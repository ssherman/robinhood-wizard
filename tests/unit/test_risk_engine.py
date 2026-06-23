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
    return {
        symbol: SymbolRisk(
            symbol=symbol,
            price=Decimal(price),
            average_volume=Decimal(volume),
            market_cap=Decimal(cap),
        )
    }


def test_valid_buy_within_band_is_approved():
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="AAPL", quantity="10", limit_price="100.20")]
    )
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
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="101")]
    )
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "slippage" in result.rejected[0].reason.lower()


def test_trades_per_cycle_caps_approvals():
    # 6 small valid buys, policy allows 5; the 6th is rejected for the trade cap.
    intents = [
        TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100") for _ in range(6)
    ]
    result = vet(TradePlan(intents=intents), RiskPolicy(), _portfolio(), _market())
    assert len(result.approved) == 5
    assert len(result.rejected) == 1
    assert "trades" in result.rejected[0].reason.lower()


def test_no_market_data_rejected():
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="ZZZZ", quantity="1", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio(), _market())  # market has AAPL only
    assert "market data" in result.rejected[0].reason.lower()
