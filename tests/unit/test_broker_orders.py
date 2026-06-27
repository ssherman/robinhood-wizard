# tests/unit/test_broker_orders.py
from rh_wizard.broker.client import BrokerClient


class ScriptedMCPClient:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return []

    def call_tool_sync(self, *, tool_use_id, name, arguments=None):
        assert self.entered
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_review_equity_order_forwards_only_non_none():
    fake = ScriptedMCPClient([{"data": {"quote": {"last_trade_price": "190"}}}])
    with BrokerClient(fake) as broker:
        out = broker.review_equity_order(
            "ACC1", "AAPL", "buy", "limit", quantity="3", limit_price="190"
        )
    assert out  # payload returned
    name, args = fake.calls[0]
    assert name == "review_equity_order"
    assert args == {
        "account_number": "ACC1",
        "symbol": "AAPL",
        "side": "buy",
        "type": "limit",
        "quantity": "3",
        "limit_price": "190",
        "time_in_force": "gfd",
        "market_hours": "regular_hours",
    }
    assert "dollar_amount" not in args  # None params dropped


def test_place_equity_order_market_notional_with_ref_id():
    fake = ScriptedMCPClient([{"data": {"id": "ord-1"}}])
    with BrokerClient(fake) as broker:
        out = broker.place_equity_order(
            "ACC1", "MU", "buy", "market", dollar_amount="180.00", ref_id="r-1"
        )
    assert out  # payload returned
    name, args = fake.calls[0]
    assert name == "place_equity_order"
    assert args == {
        "account_number": "ACC1",
        "symbol": "MU",
        "side": "buy",
        "type": "market",
        "dollar_amount": "180.00",
        "ref_id": "r-1",
        "time_in_force": "gfd",
        "market_hours": "regular_hours",
    }
