from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.strategy import Strategy
from rh_wizard.research.base import Researcher
from rh_wizard.research.stub import StubResearcher


def _portfolio():
    return PortfolioState(
        account_number="A", positions=[], cash=Decimal("10000"), buying_power=Decimal("10000")
    )


def test_stub_is_a_researcher():
    assert isinstance(StubResearcher(), Researcher)


def test_stub_flags_resolved_universe_symbols():
    strategy = Strategy(id="m", name="M", universe=["AAPL", "ZZZZ"])
    market = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})
    report = StubResearcher().research(strategy, market, _portfolio())
    # only AAPL resolved in the market context -> only AAPL is a candidate
    assert [c.symbol for c in report.candidates] == ["AAPL"]
    assert report.summary  # non-empty stub summary


def test_stub_empty_when_nothing_resolved():
    strategy = Strategy(id="m", name="M", universe=["AAPL"])
    report = StubResearcher().research(strategy, MarketContext(), _portfolio())
    assert report.candidates == []
