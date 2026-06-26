from decimal import Decimal

from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.research import ResearchReport, Source
from rh_wizard.models.trade import TradeRecord


def _trade(order_id="O1", state="filled"):
    return TradeRecord(
        order_id=order_id,
        symbol="AAPL",
        side="buy",
        quantity=Decimal("2"),
        price=Decimal("100"),
        state=state,
        created_at="2026-01-01T00:00:00Z",
        source="agentic",
    )


def test_record_and_read_back(tmp_path):
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([_trade()])
        trades = journal.recent_trades()
    assert len(trades) == 1
    assert trades[0].order_id == "O1"
    assert trades[0].quantity == Decimal("2")
    assert trades[0].price == Decimal("100")


def test_upsert_is_idempotent(tmp_path):
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([_trade(state="confirmed")])
        journal.record_trades([_trade(state="filled")])  # same order_id, new state
        trades = journal.recent_trades()
    assert len(trades) == 1  # one row, not two
    assert trades[0].state == "filled"  # updated in place


def test_recent_trades_orders_newest_first(tmp_path):
    older = TradeRecord(
        order_id="OLD",
        symbol="A",
        side="buy",
        quantity=Decimal("1"),
        price=None,
        state="filled",
        created_at="2026-01-01",
    )
    newer = TradeRecord(
        order_id="NEW",
        symbol="B",
        side="buy",
        quantity=Decimal("1"),
        price=None,
        state="filled",
        created_at="2026-02-01",
    )
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([older, newer])
        trades = journal.recent_trades()
    assert [t.order_id for t in trades] == ["NEW", "OLD"]


def test_record_research_persists_and_reads_back_sources():
    with SqliteJournal(":memory:") as journal:
        report = ResearchReport(
            summary="ok",
            sources=[Source(title="A", url="https://a"), Source(title="B", url="https://b")],
        )
        journal.record_research("run1", report)
        rows = journal.research_sources("run1")
        assert [(r["title"], r["url"]) for r in rows] == [("A", "https://a"), ("B", "https://b")]


def test_record_research_is_idempotent_and_handles_empty():
    with SqliteJournal(":memory:") as journal:
        journal.record_research("run1", ResearchReport(sources=[Source(url="https://a")]))
        journal.record_research("run1", ResearchReport(sources=[]))  # re-record clears prior rows
        assert journal.research_sources("run1") == []


def test_record_and_read_discovery():
    from rh_wizard.models.compile import SuggestedTicker
    from rh_wizard.models.discovery import DiscoveryResult

    result = DiscoveryResult(
        tickers=[SuggestedTicker(symbol="NVDA", rationale="ai"), SuggestedTicker(symbol="MSFT")],
        sources=[Source(title="Morningstar", url="https://e/ai")],
    )
    with SqliteJournal(":memory:") as journal:
        journal.record_discovery("run1", result)
        assert [r["symbol"] for r in journal.discovered_universe("run1")] == ["NVDA", "MSFT"]
        assert [r["url"] for r in journal.discovery_sources("run1")] == ["https://e/ai"]


def test_record_discovery_is_idempotent_and_handles_empty():
    from rh_wizard.models.compile import SuggestedTicker
    from rh_wizard.models.discovery import DiscoveryResult

    with SqliteJournal(":memory:") as journal:
        journal.record_discovery("run1", DiscoveryResult(tickers=[SuggestedTicker(symbol="NVDA")]))
        journal.record_discovery("run1", DiscoveryResult(tickers=[SuggestedTicker(symbol="MSFT")]))
        assert [r["symbol"] for r in journal.discovered_universe("run1")] == ["MSFT"]  # replaced
        journal.record_discovery("run1", DiscoveryResult())  # empty clears it
        assert journal.discovered_universe("run1") == []


def test_record_allocation_roundtrips():
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.allocation import (
        AllocationRecommendation,
        AllocationReport,
        BucketAllocation,
    )
    from rh_wizard.models.research import Source

    report = AllocationReport(
        buckets=[
            BucketAllocation(
                bucket_id="ai",
                name="AI",
                target_pct=Decimal("40"),
                current_pct=Decimal("30"),
                drift_pct=Decimal("-10"),
                within_band=False,
                action="buy",
            )
        ],
        orphans=["TSLA"],
        investable=Decimal("900"),
    )
    rec = AllocationRecommendation(sources=[Source(title="N", url="https://e/x")])
    with SqliteJournal(":memory:") as j:
        j.record_allocation("run1", report, rec)
        rows = j.allocation_report("run1")
        assert rows[0]["bucket_id"] == "ai"
        assert rows[0]["action"] == "buy"
        assert rows[0]["target_pct"] == "40"
        assert [s["url"] for s in j.recommendation_sources("run1")] == ["https://e/x"]
