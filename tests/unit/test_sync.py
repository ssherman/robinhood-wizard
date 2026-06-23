from decimal import Decimal

from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.sync import sync_equity_orders


class FakeBroker:
    def __init__(self, orders):
        self._orders = orders
        self.last_kwargs = None

    def get_equity_orders(self, account_number, *, created_at_gte=None):
        self.last_kwargs = {"account_number": account_number, "created_at_gte": created_at_gte}
        return self._orders


def test_sync_writes_orders_to_journal(tmp_path):
    broker = FakeBroker(
        [
            {
                "id": "O1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "2",
                "average_price": "100",
                "state": "filled",
                "created_at": "2026-01-01",
                "placed_agent": "agentic",
            }
        ]
    )
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        count = sync_equity_orders(broker, "ACC1", journal, created_at_gte="2026-01-01")
        trades = journal.recent_trades()
    assert count == 1
    assert broker.last_kwargs == {"account_number": "ACC1", "created_at_gte": "2026-01-01"}
    assert trades[0].order_id == "O1"
    assert trades[0].symbol == "AAPL"
    assert trades[0].price == Decimal("100")
    assert trades[0].source == "agentic"


def test_sync_is_idempotent(tmp_path):
    order = {
        "id": "O1",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": "2",
        "average_price": "100",
        "state": "filled",
        "created_at": "2026-01-01",
    }
    broker = FakeBroker([order])
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        sync_equity_orders(broker, "ACC1", journal)
        sync_equity_orders(broker, "ACC1", journal)
        trades = journal.recent_trades()
    assert len(trades) == 1


def test_sync_handles_null_quantity(tmp_path):
    broker = FakeBroker(
        [
            {
                "id": "O2",
                "symbol": "TSLA",
                "side": "buy",
                "quantity": None,
                "state": "cancelled",
                "created_at": "2026-01-02",
            }
        ]
    )
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        count = sync_equity_orders(broker, "ACC1", journal)
        trades = journal.recent_trades()
    assert count == 1
    assert trades[0].quantity == Decimal("0")


def test_sync_skips_order_without_id(tmp_path):
    orders = [
        {
            "symbol": "MSFT",
            "side": "sell",
            "quantity": "1",
            "state": "filled",
            "created_at": "2026-01-03",
        },
        {
            "id": "O3",
            "symbol": "GOOG",
            "side": "buy",
            "quantity": "3",
            "state": "filled",
            "created_at": "2026-01-04",
        },
    ]
    broker = FakeBroker(orders)
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        count = sync_equity_orders(broker, "ACC1", journal)
        trades = journal.recent_trades()
    assert count == 1
    assert trades[0].order_id == "O3"
