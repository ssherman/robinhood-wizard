from decimal import Decimal

from rh_wizard.config.settings import Settings
from rh_wizard.memory.portfolio import reconcile


class FakeBroker:
    def get_accounts(self):
        return [{"account_number": "ACC1", "type": "agentic"}]

    def get_equity_positions(self, account_number):
        assert account_number == "ACC1"
        # Live shape (§18): positions carry average_buy_price, not average_cost.
        return [{"symbol": "AAPL", "quantity": "10", "average_buy_price": "100"}]

    def get_portfolio(self, account_number):
        # Live shape (§18): cash is top-level; buying_power is a nested object.
        return {
            "data": {
                "total_value": "3000",
                "equity_value": "0",
                "cash": "500.00",
                "buying_power": {
                    "buying_power": "500.00",
                    "unleveraged_buying_power": "500.00",
                    "display_currency": "USD",
                },
            }
        }


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
