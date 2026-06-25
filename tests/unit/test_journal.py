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
