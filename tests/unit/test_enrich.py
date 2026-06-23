from decimal import Decimal

from rh_wizard.memory.portfolio import enrich_with_quotes
from rh_wizard.models.portfolio import PortfolioState, Position


def _state():
    return PortfolioState(
        account_number="ACC1",
        positions=[
            Position(
                symbol="AAPL",
                quantity=Decimal("10"),
                average_cost=Decimal("100"),
                cost_basis=Decimal("1000"),
            )
        ],
        cash=Decimal("500"),
        buying_power=Decimal("500"),
    )


class FakeBroker:
    def __init__(self, quotes):
        self._quotes = quotes

    def get_equity_quotes(self, symbols):
        return self._quotes


def test_enrich_adds_market_value_and_return():
    broker = FakeBroker([{"symbol": "AAPL", "last_trade_price": "120.00"}])
    out = enrich_with_quotes(_state(), broker)
    pos = out.positions[0]
    assert pos.current_price == Decimal("120.00")
    assert pos.market_value == Decimal("1200.00")
    assert pos.unrealized_pl == Decimal("200.00")
    assert pos.unrealized_pl_pct == Decimal("20")
    assert out.market_value == Decimal("1200.00")
    assert out.total_value == Decimal("1700.00")
    assert out.total_return_pct == Decimal("20")


def test_enrich_degrades_when_quote_missing():
    broker = FakeBroker([])  # no quote for AAPL
    out = enrich_with_quotes(_state(), broker)
    assert out.positions[0].current_price is None
    assert out.market_value is None
    assert out.total_value is None
