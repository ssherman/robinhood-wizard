from decimal import Decimal

from rh_wizard.config.settings import Settings
from rh_wizard.memory.portfolio import reconcile


class FakeBroker:
    def get_accounts(self):
        return [{"account_number": "ACC1", "type": "agentic"}]

    def get_equity_positions(self, account_number):
        assert account_number == "ACC1"
        return [{"symbol": "AAPL", "quantity": "10", "average_cost": "100"}]

    def get_portfolio(self, account_number):
        return {"data": {"cash": "500.00", "buying_power": "500.00"}}


def test_reconcile_builds_portfolio_state():
    state = reconcile(FakeBroker(), Settings())
    assert state.account_number == "ACC1"
    assert len(state.positions) == 1
    assert state.positions[0].symbol == "AAPL"
    assert state.positions[0].quantity == Decimal("10")
    assert state.positions[0].cost_basis == Decimal("1000")
    assert state.cash == Decimal("500.00")
    assert state.buying_power == Decimal("500.00")
    # No quotes yet — enrichment fields are None.
    assert state.market_value is None
