from decimal import Decimal

from rh_wizard.models.portfolio import PortfolioState, Position


def test_position_coerces_string_numbers_to_decimal():
    p = Position(symbol="AAPL", quantity="10", average_cost="100.25", cost_basis="1002.50")
    assert p.quantity == Decimal("10")
    assert p.average_cost == Decimal("100.25")
    assert p.current_price is None  # enrichment fields default to None


def test_portfolio_state_defaults():
    state = PortfolioState(
        account_number="ACC1",
        positions=[],
        cash=Decimal("500"),
        buying_power=Decimal("500"),
    )
    assert state.positions == []
    assert state.market_value is None
    assert state.total_value is None
