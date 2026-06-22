from rh_wizard.broker.client import BrokerClient


class ScriptedMCPClient:
    """Returns queued raw tool results in order and records each call's args."""

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
        assert self.entered, "must be used inside the client context"
        assert tool_use_id
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_get_portfolio_returns_payload():
    result = {"data": {"buying_power": "500.00", "cash": "250.00"}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        payload = broker.get_portfolio("ACC1")
    assert payload["data"]["buying_power"] == "500.00"
    assert fake.calls[0] == ("get_portfolio", {"account_number": "ACC1"})


def test_get_equity_positions_paginates():
    page1 = {"data": {"positions": [{"symbol": "AAPL"}], "next": "https://x/y?cursor=abc"}}
    page2 = {"data": {"positions": [{"symbol": "MSFT"}], "next": None}}
    fake = ScriptedMCPClient([page1, page2])
    with BrokerClient(fake) as broker:
        positions = broker.get_equity_positions("ACC1")
    assert [p["symbol"] for p in positions] == ["AAPL", "MSFT"]
    # second page carried the cursor extracted from page1's next URL
    assert fake.calls[1] == ("get_equity_positions", {"account_number": "ACC1", "cursor": "abc"})


def test_get_equity_quotes_unwraps_nested_quote():
    # Live shape (§18): data.results[] pairs {"quote": {...}, "close": {...}};
    # get_equity_quotes unwraps to the inner quote dict.
    result = {
        "data": {
            "results": [
                {
                    "quote": {"symbol": "AAPL", "last_trade_price": "190.00"},
                    "close": {"symbol": "AAPL", "price": "189.00"},
                }
            ]
        }
    }
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        quotes = broker.get_equity_quotes(["AAPL"])
    assert quotes[0]["symbol"] == "AAPL"
    assert quotes[0]["last_trade_price"] == "190.00"
    assert fake.calls[0] == ("get_equity_quotes", {"symbols": ["AAPL"]})


def test_get_equity_quotes_tolerates_flat_shape():
    # Defensive: a flat {"quotes": [...]} shape still works.
    result = {"data": {"quotes": [{"symbol": "MSFT", "last_trade_price": "400.00"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        quotes = broker.get_equity_quotes(["MSFT"])
    assert quotes[0]["symbol"] == "MSFT"


def test_get_equity_quotes_empty_short_circuits():
    fake = ScriptedMCPClient([])  # no result needed; should not call the tool
    with BrokerClient(fake) as broker:
        assert broker.get_equity_quotes([]) == []
    assert fake.calls == []


def test_get_equity_orders_paginates_and_forwards_filters():
    page1 = {"data": {"orders": [{"id": "O1"}], "next": "https://x/y?cursor=n2"}}
    page2 = {"data": {"orders": [{"id": "O2"}], "next": None}}
    fake = ScriptedMCPClient([page1, page2])
    with BrokerClient(fake) as broker:
        orders = broker.get_equity_orders("ACC1", created_at_gte="2026-01-01")
    assert [o["id"] for o in orders] == ["O1", "O2"]
    assert fake.calls[0] == (
        "get_equity_orders",
        {"account_number": "ACC1", "created_at_gte": "2026-01-01"},
    )
    assert fake.calls[1][1]["cursor"] == "n2"
