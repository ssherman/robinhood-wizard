# tests/unit/test_broker_fundamentals.py
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
        assert self.entered
        assert tool_use_id
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_get_equity_fundamentals_returns_list_and_forwards_symbols():
    result = {"data": {"results": [{"symbol": "AAPL", "market_cap": "3.0E12"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_fundamentals(["AAPL"])
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["market_cap"] == "3.0E12"
    assert fake.calls[0] == ("get_equity_fundamentals", {"symbols": ["AAPL"]})


def test_get_equity_fundamentals_tolerates_fundamentals_key():
    result = {"data": {"fundamentals": [{"symbol": "MSFT", "pe_ratio": "35"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_fundamentals(["MSFT"])
    assert rows[0]["symbol"] == "MSFT"


def test_get_equity_fundamentals_empty_short_circuits():
    fake = ScriptedMCPClient([])  # no result needed; must not call the tool
    with BrokerClient(fake) as broker:
        assert broker.get_equity_fundamentals([]) == []
    assert fake.calls == []
