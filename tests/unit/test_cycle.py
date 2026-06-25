# tests/unit/test_cycle.py
from rh_wizard.config.settings import Settings
from rh_wizard.core.cycle import CycleDeps, run_cycle
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import RISK_SIGNALS, Signal
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.stub import StubPlanner
from rh_wizard.research.stub import StubResearcher


class FakeBroker:
    def __init__(self, raise_accounts=False):
        self._raise = raise_accounts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_accounts(self):
        if self._raise:
            raise RuntimeError("broker down")
        return [{"account_number": "ACC1", "agentic_allowed": True}]

    def get_equity_positions(self, account_number):
        return []

    def get_portfolio(self, account_number):
        return {"data": {"cash": "10000", "buying_power": "10000"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "100"} for s in symbols]


class FakeDataSource:
    name = "fake"

    def provides(self):
        return set(RISK_SIGNALS) | {Signal.PRICE}

    def fetch(self, symbols, signals):
        return {
            s: SymbolData(
                symbol=s, price="100", average_volume="50000000", market_cap="3000000000000"
            )
            for s in symbols
        }


def _deps(journal, broker=None):
    return CycleDeps(
        broker=broker or FakeBroker(),
        settings=Settings(),
        resolver=SignalResolver([FakeDataSource()]),
        researcher=StubResearcher(),
        planner=StubPlanner(),
        journal=journal,
    )


def test_cycle_completes_and_vets_a_plan():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert result.run.finished_at is not None
        # 1-share AAPL buy at $100 is within all guardrails -> approved
        assert [i.symbol for i in result.vetted.approved] == ["AAPL"]
        # the run + plan were journaled
        assert journal.recent_runs()[0].run_id == result.run.run_id
        symbols = {row["symbol"] for row in journal.plan_intents(result.run.run_id)}
        assert symbols == {"AAPL"}


def test_cycle_aborts_when_reconcile_fails():
    strategy = Strategy(id="m", name="M", universe=["AAPL"])
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal, broker=FakeBroker(raise_accounts=True))
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "broker down" in result.run.note
        assert result.vetted is None
        # the aborted run is still journaled
        assert journal.recent_runs()[0].status == "aborted"


def test_cycle_includes_held_symbols_in_universe():
    # AAPL already held -> stub planner won't buy it; universe still resolves it.
    strategy = Strategy(id="m", name="M", universe=["MSFT"], signals_needed={Signal.PRICE})

    class HeldBroker(FakeBroker):
        def get_equity_positions(self, account_number):
            return [{"symbol": "AAPL", "quantity": "5", "average_cost": "90"}]

    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal, broker=HeldBroker())
        with deps.broker:
            result = run_cycle(strategy, deps)
        # MSFT (new) approved; AAPL held so not bought
        assert [i.symbol for i in result.vetted.approved] == ["MSFT"]
        assert "AAPL" in result.market.symbols  # held symbol was resolved


def test_cycle_aborts_when_research_raises():
    from rh_wizard.core.cycle import run_cycle
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy

    class BoomResearcher:
        def research(self, strategy, market, portfolio):
            raise RuntimeError("llm down")

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.researcher = BoomResearcher()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "llm down" in result.run.note
        assert result.vetted is None
        assert journal.recent_runs()[0].status == "aborted"


def test_cycle_records_research_sources():
    from rh_wizard.models.research import Candidate, ResearchReport, Source

    class SourcedResearcher:
        def research(self, strategy, market, portfolio):
            return ResearchReport(
                candidates=[Candidate(symbol="AAPL", thesis="fit")],
                summary="ok",
                sources=[Source(title="N", url="https://news/aapl")],
            )

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.researcher = SourcedResearcher()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        rows = journal.research_sources(result.run.run_id)
        assert [r["url"] for r in rows] == ["https://news/aapl"]
