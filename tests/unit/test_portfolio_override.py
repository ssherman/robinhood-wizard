from decimal import Decimal

from rh_wizard.memory.portfolio import PortfolioOverride, apply_override
from rh_wizard.models.portfolio import PortfolioState, Position


def _state():
    return PortfolioState(
        account_number="ACC1",
        positions=[Position(symbol="AAPL", quantity="5", average_cost="90", cost_basis="450")],
        cash=Decimal("1000"),
        buying_power=Decimal("1000"),
    )


def test_inactive_override_is_identity():
    override = PortfolioOverride()
    assert override.active is False
    out = apply_override(_state(), override)
    assert out.cash == Decimal("1000")
    assert out.buying_power == Decimal("1000")
    assert [p.symbol for p in out.positions] == ["AAPL"]


def test_capital_overrides_cash_and_buying_power_as_decimal():
    override = PortfolioOverride(capital=Decimal("10000"))
    assert override.active is True
    out = apply_override(_state(), override)
    assert out.cash == Decimal("10000")
    assert out.buying_power == Decimal("10000")
    assert isinstance(out.cash, Decimal)
    # holdings untouched when only capital is set
    assert [p.symbol for p in out.positions] == ["AAPL"]


def test_ignore_holdings_empties_positions_keeps_cash():
    override = PortfolioOverride(ignore_holdings=True)
    assert override.active is True
    out = apply_override(_state(), override)
    assert out.positions == []
    assert out.cash == Decimal("1000")  # real cash preserved


def test_both_compose():
    override = PortfolioOverride(capital=Decimal("10000"), ignore_holdings=True)
    out = apply_override(_state(), override)
    assert out.positions == []
    assert out.cash == Decimal("10000")
    assert out.buying_power == Decimal("10000")
