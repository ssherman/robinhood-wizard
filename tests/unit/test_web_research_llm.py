from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, Source
from rh_wizard.models.strategy import Strategy
from rh_wizard.research.base import Researcher
from rh_wizard.research.web_llm import WEB_RESEARCH_SYSTEM, WebLlmResearcher


class FakeWebSearchLlm:
    def __init__(self):
        self.last_prompt = None
        self.last_system = None

    def research(self, output_model, prompt, system=""):
        self.last_prompt = prompt
        self.last_system = system
        report = output_model(candidates=[Candidate(symbol="AAPL", thesis="fit")], summary="ok")
        return report, [Source(title="News", url="https://news.example/aapl")]


def _market():
    return MarketContext(
        requested=[],
        symbols={"AAPL": SymbolData(symbol="AAPL", price="100", pe_ratio="30")},
        unmet_signals=[],
        notes=[],
    )


def _portfolio():
    return PortfolioState(
        account_number="ACC1",
        positions=[],
        cash=Decimal("1000"),
        buying_power=Decimal("1000"),
    )


def test_research_attaches_sources_and_returns_report():
    fake = FakeWebSearchLlm()
    researcher = WebLlmResearcher(fake)
    strategy = Strategy(id="m", name="M", intent="buy tech", universe=["AAPL"])
    report = researcher.research(strategy, _market(), _portfolio())
    assert [c.symbol for c in report.candidates] == ["AAPL"]
    assert [s.url for s in report.sources] == ["https://news.example/aapl"]
    assert fake.last_system == WEB_RESEARCH_SYSTEM
    assert "buy tech" in fake.last_prompt
    assert "AAPL" in fake.last_prompt


def test_satisfies_researcher_protocol():
    assert isinstance(WebLlmResearcher(FakeWebSearchLlm()), Researcher)
