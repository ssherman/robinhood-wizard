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


def test_position_cap_rejects_oversized_buy():
    # portfolio 10000, max 20% => $2000 cap; buy 30 * 100 = 3000 > 2000
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="AAPL", quantity="30", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "position" in result.rejected[0].reason.lower()


def test_position_cap_counts_existing_holding():
    from rh_wizard.models.portfolio import Position

    held = Position(
        symbol="AAPL", quantity="15", average_cost="100", cost_basis="1500", market_value="1500"
    )
    # cash 8500 + position 1500 = 10000 total; existing 1500 + buy 600 = 2100 > 2000 (20%)
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="AAPL", quantity="6", limit_price="100")]
    )
    result = vet(plan, RiskPolicy(), _portfolio(cash="8500", positions=[held]), _market())
    assert "position" in result.rejected[0].reason.lower()


def test_cash_reserve_rejects_buy_that_breaches_reserve():
    # Raise position + deploy caps so ONLY the cash reserve can trip:
    # portfolio 10000, reserve 10% => keep >= 1000; buy 9500 leaves 500 < 1000.
    policy = RiskPolicy(max_position_pct="100", max_deploy_pct_per_cycle="100")
    plan = TradePlan(
        intents=[
            TradeIntent(side="buy", symbol="AAPL", amount="9500", quantity="95", limit_price="100")
        ]
    )
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
    plan = TradePlan(intents=[TradeIntent(side="buy", symbol="PNY", quantity="1", limit_price="2")])
    market = _market("PNY", price="2")  # price 2 < min_price 5
    result = vet(plan, RiskPolicy(), _portfolio(), market)
    assert "liquidity" in result.rejected[0].reason.lower()


def test_liquidity_floor_rejects_thin_volume_and_small_cap():
    low_vol = _market("AAPL", volume="100")  # < 1M
    intent = TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100")
    assert (
        "liquidity"
        in vet(
            TradePlan(intents=[intent]),
            RiskPolicy(),
            _portfolio(),
            low_vol,
        )
        .rejected[0]
        .reason.lower()
    )
    small_cap = _market("AAPL", cap="100")  # < 1B
    assert (
        "liquidity"
        in vet(
            TradePlan(intents=[intent]),
            RiskPolicy(),
            _portfolio(),
            small_cap,
        )
        .rejected[0]
        .reason.lower()
    )


def test_unsizable_buy_rejected():
    # no amount and no quantity => cannot size
    plan = TradePlan(intents=[TradeIntent(side="buy", symbol="AAPL", limit_price="100")])
    result = vet(plan, RiskPolicy(), _portfolio(), _market())
    assert "size" in result.rejected[0].reason.lower()
