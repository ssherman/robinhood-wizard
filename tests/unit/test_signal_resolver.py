# tests/unit/test_signal_resolver.py
from decimal import Decimal

from rh_wizard.data.resolver import SignalResolver
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


class FakeSource:
    def __init__(self, name, provided, rows=None, raises=False):
        self.name = name
        self._provided = set(provided)
        self._rows = rows or {}
        self._raises = raises
        self.fetch_calls = 0

    def provides(self):
        return set(self._provided)

    def fetch(self, symbols, signals):
        self.fetch_calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return {s: self._rows[s] for s in symbols if s in self._rows}


def test_resolve_merges_two_sources():
    prices = FakeSource("quotes", {Signal.PRICE}, {"AAPL": SymbolData(symbol="AAPL", price="190")})
    fundamentals = FakeSource(
        "fundamentals",
        {Signal.MARKET_CAP},
        {"AAPL": SymbolData(symbol="AAPL", market_cap="3.0E12")},
    )
    ctx = SignalResolver([prices, fundamentals]).resolve(
        ["AAPL"], {Signal.PRICE, Signal.MARKET_CAP}
    )
    assert ctx.symbols["AAPL"].price == Decimal("190")
    assert ctx.symbols["AAPL"].market_cap == Decimal("3.0E12")
    assert ctx.unmet_signals == []
    assert ctx.notes == []


def test_resolve_records_unmet_signal_with_no_provider():
    prices = FakeSource("quotes", {Signal.PRICE}, {"AAPL": SymbolData(symbol="AAPL", price="190")})
    ctx = SignalResolver([prices]).resolve(["AAPL"], {Signal.PRICE, Signal.EARNINGS})
    assert ctx.unmet_signals == [Signal.EARNINGS]
    assert ctx.symbols["AAPL"].price == Decimal("190")  # still resolves what it can


def test_resolve_skips_source_not_covering_needed_signals():
    fundamentals = FakeSource(
        "fundamentals",
        {Signal.MARKET_CAP},
        {"AAPL": SymbolData(symbol="AAPL", market_cap="3.0E12")},
    )
    ctx = SignalResolver([fundamentals]).resolve(["AAPL"], {Signal.PRICE})
    assert fundamentals.fetch_calls == 0  # provides ∩ needed is empty
    assert ctx.unmet_signals == [Signal.PRICE]


def test_resolve_degrades_on_source_error():
    good = FakeSource("quotes", {Signal.PRICE}, {"AAPL": SymbolData(symbol="AAPL", price="190")})
    bad = FakeSource("fundamentals", {Signal.MARKET_CAP}, raises=True)
    ctx = SignalResolver([good, bad]).resolve(["AAPL"], {Signal.PRICE, Signal.MARKET_CAP})
    assert ctx.symbols["AAPL"].price == Decimal("190")  # the good source still applied
    assert any("fundamentals fetch failed" in n for n in ctx.notes)
    # MARKET_CAP had a provider (it just errored) -> a note, NOT an unmet signal
    assert Signal.MARKET_CAP not in ctx.unmet_signals


def test_resolve_seeds_every_universe_symbol():
    ctx = SignalResolver([]).resolve(["AAPL", "MSFT"], {Signal.PRICE})
    assert set(ctx.symbols) == {"AAPL", "MSFT"}
    assert ctx.symbols["AAPL"].price is None
    assert ctx.requested == [Signal.PRICE]
    assert ctx.unmet_signals == [Signal.PRICE]  # no sources at all
