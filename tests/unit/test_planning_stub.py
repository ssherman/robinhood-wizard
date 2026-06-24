from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState, Position
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.base import Planner
from rh_wizard.planning.stub import StubPlanner


def _market():
    return MarketContext(
        symbols={
            "AAPL": SymbolData(symbol="AAPL", price="190"),
            "MSFT": SymbolData(symbol="MSFT", price="400"),
        }
    )


def _portfolio(positions=None):
    return PortfolioState(
        account_number="A",
        positions=positions or [],
        cash=Decimal("10000"),
        buying_power=Decimal("10000"),
    )


def _report(*symbols):
    return ResearchReport(candidates=[Candidate(symbol=s) for s in symbols])


def test_stub_is_a_planner():
    assert isinstance(StubPlanner(), Planner)


def test_stub_proposes_one_share_buy_per_candidate_at_market():
    plan = StubPlanner().plan(
        Strategy(id="m", name="M"), _report("AAPL", "MSFT"), _market(), _portfolio()
    )
    by_symbol = {i.symbol: i for i in plan.intents}
    assert set(by_symbol) == {"AAPL", "MSFT"}
    assert by_symbol["AAPL"].side == "buy"
    assert by_symbol["AAPL"].quantity == Decimal("1")
    assert by_symbol["AAPL"].limit_price == Decimal("190")  # at current market price


def test_stub_skips_already_held_symbols():
    held = Position(symbol="AAPL", quantity="5", average_cost="100", cost_basis="500")
    plan = StubPlanner().plan(
        Strategy(id="m", name="M"), _report("AAPL", "MSFT"), _market(), _portfolio([held])
    )
    assert [i.symbol for i in plan.intents] == ["MSFT"]


def test_stub_skips_candidates_without_a_price():
    market = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL")})  # price is None
    plan = StubPlanner().plan(Strategy(id="m", name="M"), _report("AAPL"), market, _portfolio())
    assert plan.intents == []
