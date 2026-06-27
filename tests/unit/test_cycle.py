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
        return set(RISK_SIGNALS) | {Signal.PRICE, Signal.FRACTIONABLE}

    def fetch(self, symbols, signals):
        return {
            s: SymbolData(
                symbol=s,
                price="100",
                average_volume="50000000",
                market_cap="3000000000000",
                fractionable=True,
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


def test_cycle_unions_discovered_universe_and_journals_it():
    from rh_wizard.models.compile import SuggestedTicker
    from rh_wizard.models.discovery import DiscoveryResult

    class FakeDiscoverer:
        def discover(self, strategy):
            return DiscoveryResult(
                tickers=[SuggestedTicker(symbol="NVDA", rationale="ai")], sources=[]
            )

    strategy = Strategy(
        id="m", name="M", universe=["MSFT"], discover=True, signals_needed={Signal.PRICE}
    )
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.discoverer = FakeDiscoverer()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert "NVDA" in result.market.symbols  # discovered
        assert "MSFT" in result.market.symbols  # explicit
        assert result.discovery is not None
        assert [r["symbol"] for r in journal.discovered_universe(result.run.run_id)] == ["NVDA"]


def test_cycle_degrades_when_discovery_raises():
    class BoomDiscoverer:
        def discover(self, strategy):
            raise RuntimeError("discovery down")

    strategy = Strategy(
        id="m", name="M", universe=["AAPL"], discover=True, signals_needed={Signal.PRICE}
    )
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.discoverer = BoomDiscoverer()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"  # degrade, NOT abort
        assert any("discovery failed" in n for n in result.market.notes)
        assert [i.symbol for i in result.vetted.approved] == ["AAPL"]  # explicit universe used


def test_cycle_skips_discovery_when_flag_off():
    class BoomDiscoverer:
        def discover(self, strategy):
            raise AssertionError("discoverer must not be called when discover=False")

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.discoverer = BoomDiscoverer()  # present but must not be called
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert result.discovery is None


def _bucketed_strategy():
    from rh_wizard.models.bucket import Bucket

    return Strategy(
        id="b",
        name="B",
        signals_needed={Signal.PRICE},
        buckets=[Bucket(id="ai", target_pct="100", universe=["AAPL"])],
    )


class _FakeRecommender:
    def __init__(self, weight="100"):
        self._weight = weight

    def recommend(self, strategy, bucket_candidates, market, portfolio):
        from rh_wizard.models.allocation import (
            AllocationRecommendation,
            BucketRecommendation,
            RecommendedPosition,
        )

        return AllocationRecommendation(
            buckets=[
                BucketRecommendation(
                    bucket_id="ai",
                    positions=[RecommendedPosition(symbol="AAPL", weight=self._weight)],
                )
            ],
            summary="ok",
        )


def test_bucketed_cycle_completes_allocates_and_journals():
    strategy = _bucketed_strategy()
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.recommender = _FakeRecommender()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert result.recommendation is not None
        assert result.allocation is not None
        assert result.allocation.buckets[0].bucket_id == "ai"
        # investable = 10000 * 0.9 = 9000, single bucket 100% -> a buy intent exists, vetted
        all_intents = result.vetted.approved + [r.intent for r in result.vetted.rejected]
        assert any(i.side == "buy" and i.symbol == "AAPL" for i in all_intents)
        assert journal.allocation_report(result.run.run_id)[0]["bucket_id"] == "ai"


def test_bucketed_cycle_aborts_when_recommender_raises():
    class Boom:
        def recommend(self, strategy, bucket_candidates, market, portfolio):
            raise RuntimeError("rec down")

    strategy = _bucketed_strategy()
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.recommender = Boom()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "rec down" in result.run.note


def test_bucketed_cycle_degrades_when_bucket_discovery_raises():
    from rh_wizard.models.bucket import Bucket

    class BoomDiscoverer:
        def discover(self, strategy):
            raise RuntimeError("discovery down")

    strategy = Strategy(
        id="b",
        name="B",
        signals_needed={Signal.PRICE},
        buckets=[Bucket(id="ai", target_pct="100", universe=["AAPL"], discover=True)],
    )
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.recommender = _FakeRecommender()
        deps.discoverer = BoomDiscoverer()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"  # degrade, not abort
        assert any("discovery failed" in n for n in result.market.notes)
        assert "AAPL" in result.market.symbols  # explicit bucket universe still resolved


def test_bucketed_cycle_aborts_when_recommender_missing():
    strategy = _bucketed_strategy()
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)  # recommender defaults to None
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "requires a recommender" in result.run.note
        assert journal.recent_runs()[0].status == "aborted"


def test_flat_cycle_unchanged_has_no_allocation():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert result.allocation is None
        assert result.recommendation is None


class _YesGate:
    def confirm(self, vetted, portfolio, account):
        self.account = account
        return True


class _NoGate:
    def confirm(self, vetted, portfolio, account):
        return False


class _RecordingExecutor:
    def __init__(self, review_ok=True, place_fails=False):
        self._review_ok = review_ok
        self._place_fails = place_fails
        self.reviewed = []
        self.placed = []

    def review(self, intent, account):
        from rh_wizard.models.order import ReviewResult

        self.reviewed.append(intent.symbol)
        return ReviewResult(ok=self._review_ok, alerts=[] if self._review_ok else ["blocked"])

    def place(self, intent, account, ref_id):
        from rh_wizard.models.order import OrderResult

        self.placed.append((intent.symbol, ref_id))
        status = "failed" if self._place_fails else "placed"
        return OrderResult(
            symbol=intent.symbol,
            side=intent.side,
            status=status,
            order_type="limit",
            quantity=intent.quantity,
            ref_id=ref_id,
            order_id=None if self._place_fails else "ord",
        )


def _human_approval():
    from rh_wizard.models.cycle import CycleMode

    return CycleMode.HUMAN_APPROVAL


def test_dryrun_never_executes():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps)  # default DryRun
        assert result.orders == []
        assert ex.placed == []  # executor never called in DryRun
        assert ex.reviewed == []  # review is also never called in DryRun


def test_human_approval_places_approved_orders():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.run.status == "completed"
        assert [o.symbol for o in result.orders] == ["AAPL"]
        assert result.orders[0].status == "placed"
        assert ex.placed and ex.placed[0][1]  # a ref_id was passed
        assert deps.approval.account == "ACC1"  # the reconciled agentic account
        assert journal.orders(result.run.run_id)[0]["status"] == "placed"


def test_human_approval_declined_places_nothing():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _NoGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.orders == []
        assert ex.placed == []


def test_review_alert_skips_order():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor(review_ok=False)
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.orders[0].status == "skipped"
        assert ex.placed == []  # never placed after a blocking review


def test_place_failure_halts_remaining():
    # Two approved intents; the first place fails -> the second is never attempted.
    strategy = Strategy(id="m", name="M", universe=["AAPL", "MSFT"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor(place_fails=True)
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        statuses = [o.status for o in result.orders]
        assert statuses == ["failed"]  # halted after the first failure
        assert len(ex.placed) == 1  # the second was not attempted


def test_human_approval_places_orders_from_bucketed_path():
    from rh_wizard.models.bucket import Bucket

    # 10% target -> investable $9000 * 10% = $900 -> 9% of $10000 portfolio < 20% cap -> approved
    strategy = Strategy(
        id="b",
        name="B",
        signals_needed={Signal.PRICE},
        buckets=[Bucket(id="ai", target_pct="10", universe=["AAPL"])],
    )
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.recommender = _FakeRecommender()
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            result = run_cycle(strategy, deps, _human_approval())
        assert result.run.status == "completed"
        assert [o.symbol for o in result.orders] == ["AAPL"]  # bucketed path reached the executor
        assert result.orders[0].status == "placed"
        assert ex.placed  # the executor was actually invoked from _run_bucketed
        assert journal.orders(result.run.run_id)[0]["status"] == "placed"
