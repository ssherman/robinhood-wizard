from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.base import Planner
from rh_wizard.planning.llm import LlmPlanner


class FakeLlm:
    def __init__(self, plan):
        self._plan = plan
        self.last_prompt = None

    def generate(self, output_model, prompt, system=""):
        assert output_model is TradePlan
        self.last_prompt = prompt
        return self._plan


def _market():
    return MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})


def _portfolio():
    return PortfolioState(
        account_number="A", positions=[], cash=Decimal("10000"), buying_power=Decimal("10000")
    )


def test_llm_planner_is_a_planner():
    assert isinstance(LlmPlanner(FakeLlm(TradePlan())), Planner)


def test_plan_passes_report_and_returns_plan():
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="AAPL", quantity="2", limit_price="190")],
        rationale="thesis fit",
    )
    fake = FakeLlm(plan)
    report = ResearchReport(candidates=[Candidate(symbol="AAPL", thesis="cheap")], summary="s")
    out = LlmPlanner(fake).plan(Strategy(id="m", name="M"), report, _market(), _portfolio())
    assert out is plan
    assert "AAPL" in fake.last_prompt  # candidate surfaced into the prompt
    assert "190" in fake.last_prompt  # current price available for limit pricing


def test_candidate_lines_handles_missing_price():
    from rh_wizard.planning.llm import _candidate_lines

    report = ResearchReport(candidates=[Candidate(symbol="ZZZ", thesis="t")])
    out = "\n".join(_candidate_lines(report, MarketContext(symbols={})))
    assert "price=None" not in out
    assert "price=unknown" in out
