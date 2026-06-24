from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.research.base import Researcher
from rh_wizard.research.llm import LlmResearcher


class FakeLlm:
    def __init__(self, report):
        self._report = report
        self.last_prompt = None
        self.last_system = None

    def generate(self, output_model, prompt, system=""):
        assert output_model is ResearchReport
        self.last_prompt = prompt
        self.last_system = system
        return self._report


def _market():
    return MarketContext(
        symbols={
            "AAPL": SymbolData(symbol="AAPL", price="190", pe_ratio="30", sector="Technology"),
        }
    )


def _portfolio():
    return PortfolioState(
        account_number="A", positions=[], cash=Decimal("10000"), buying_power=Decimal("10000")
    )


def test_llm_researcher_is_a_researcher():
    assert isinstance(LlmResearcher(FakeLlm(ResearchReport())), Researcher)


def test_research_builds_prompt_and_returns_report():
    report = ResearchReport(candidates=[Candidate(symbol="AAPL")], summary="ok")
    fake = FakeLlm(report)
    strategy = Strategy(id="m", name="M", intent="buy quality tech", universe=["AAPL"])
    out = LlmResearcher(fake).research(strategy, _market(), _portfolio())
    assert out is report
    assert "buy quality tech" in fake.last_prompt  # intent in prompt
    assert "AAPL" in fake.last_prompt  # resolved symbol in prompt
    assert fake.last_system  # non-empty system prompt
