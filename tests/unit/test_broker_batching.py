# tests/unit/test_broker_batching.py
"""Robinhood's per-symbol equity tools cap at 10 symbols per call (get_equity_fundamentals /
get_equity_tradability) — the broker must split larger universes into <=10-symbol chunks and
concatenate. get_equity_tradability additionally requires an account_number. Bucketed
strategies (Phase 4e) routinely resolve >10 symbols, so this batching is load-bearing.
"""

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
        self.calls.append((name, arguments))
        return self._results.pop(0)


def _fundamentals_page(symbols):
    return {"data": {"results": [{"symbol": s, "average_volume": "5000000"} for s in symbols]}}


def test_get_equity_fundamentals_batches_to_10_per_call():
    syms = [f"S{i}" for i in range(23)]  # 23 -> chunks of 10, 10, 3
    fake = ScriptedMCPClient(
        [
            _fundamentals_page(syms[0:10]),
            _fundamentals_page(syms[10:20]),
            _fundamentals_page(syms[20:23]),
        ]
    )
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_fundamentals(syms)
    assert [r["symbol"] for r in rows] == syms  # all 23, concatenated in order
    assert [len(args["symbols"]) for _, args in fake.calls] == [10, 10, 3]
    assert all(name == "get_equity_fundamentals" for name, _ in fake.calls)


def test_get_equity_quotes_batches_to_10_per_call():
    syms = [f"S{i}" for i in range(15)]

    def page(symbols):
        return {
            "data": {
                "results": [{"quote": {"symbol": s, "last_trade_price": "1"}} for s in symbols]
            }
        }

    fake = ScriptedMCPClient([page(syms[0:10]), page(syms[10:15])])
    with BrokerClient(fake) as broker:
        quotes = broker.get_equity_quotes(syms)
    assert [q["symbol"] for q in quotes] == syms
    assert [len(args["symbols"]) for _, args in fake.calls] == [10, 5]


def test_get_equity_tradability_forwards_account_number_and_batches():
    syms = [f"S{i}" for i in range(12)]

    def page(symbols):
        return {
            "data": {
                "results": [{"symbol": s, "fractional_tradability": "tradable"} for s in symbols]
            }
        }

    fake = ScriptedMCPClient([page(syms[0:10]), page(syms[10:12])])
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_tradability("ACC1", syms)
    assert [r["symbol"] for r in rows] == syms
    assert len(fake.calls) == 2
    for name, args in fake.calls:
        assert name == "get_equity_tradability"
        assert args["account_number"] == "ACC1"
        assert len(args["symbols"]) <= 10


def test_batched_calls_short_circuit_on_empty():
    fake = ScriptedMCPClient([])  # no results queued; nothing should be called
    with BrokerClient(fake) as broker:
        assert broker.get_equity_fundamentals([]) == []
        assert broker.get_equity_quotes([]) == []
        assert broker.get_equity_tradability("ACC1", []) == []
    assert fake.calls == []
