# tests/unit/test_robinhood_source.py
from decimal import Decimal

from rh_wizard.data.robinhood import RobinhoodDataSource
from rh_wizard.models.signals import Signal


class FakeBroker:
    def __init__(self):
        self.quote_calls = 0
        self.fundamentals_calls = 0

    def get_equity_quotes(self, symbols):
        self.quote_calls += 1
        return [{"symbol": s, "last_trade_price": "190.00"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        self.fundamentals_calls += 1
        return [
            {
                "symbol": s,
                "average_volume": "50000000",
                "market_cap": "3.0E12",
                "pe_ratio": "30",
                "sector": "Technology",
            }
            for s in symbols
        ]


def test_provides_lists_the_implemented_signals():
    src = RobinhoodDataSource(FakeBroker())
    provided = src.provides()
    assert Signal.PRICE in provided
    assert Signal.MARKET_CAP in provided
    assert Signal.DIVIDEND_YIELD in provided
    # declared seams are NOT provided
    assert Signal.NEWS not in provided
    assert Signal.HISTORICALS not in provided


def test_fetch_populates_price_from_quotes_and_facts_from_fundamentals():
    src = RobinhoodDataSource(FakeBroker())
    data = src.fetch(["AAPL"], {Signal.PRICE, Signal.MARKET_CAP, Signal.SECTOR})
    d = data["AAPL"]
    assert d.price == Decimal("190.00")
    assert d.market_cap == Decimal("3.0E12")
    assert d.sector == "Technology"


def test_fetch_only_quotes_when_only_price_requested():
    broker = FakeBroker()
    RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.PRICE})
    assert broker.quote_calls == 1
    assert broker.fundamentals_calls == 0


def test_fetch_only_fundamentals_when_price_not_requested():
    broker = FakeBroker()
    RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.MARKET_CAP})
    assert broker.quote_calls == 0
    assert broker.fundamentals_calls == 1


def test_fetch_ignores_unprovided_signals():
    broker = FakeBroker()
    # NEWS is not provided -> nothing requested that needs a call
    data = RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.NEWS})
    assert broker.quote_calls == 0
    assert broker.fundamentals_calls == 0
    assert data == {}


def test_fetch_empty_symbols_returns_empty():
    broker = FakeBroker()
    assert RobinhoodDataSource(broker).fetch([], {Signal.PRICE}) == {}
    assert broker.quote_calls == 0


def test_fetch_leaves_missing_facts_as_none():
    class ThinBroker(FakeBroker):
        def get_equity_fundamentals(self, symbols):
            return [{"symbol": s, "market_cap": "3.0E12"} for s in symbols]  # no pe_ratio

    data = RobinhoodDataSource(ThinBroker()).fetch(["AAPL"], {Signal.MARKET_CAP, Signal.PE_RATIO})
    assert data["AAPL"].market_cap == Decimal("3.0E12")
    assert data["AAPL"].pe_ratio is None
