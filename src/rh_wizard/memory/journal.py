"""SQLite-backed trade journal (spec §6).

Stores one row per known broker order, keyed by order_id (idempotent upsert). Decimal
fields are stored as TEXT to avoid float precision loss.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from rh_wizard.models.trade import TradeRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    order_id   TEXT PRIMARY KEY,
    symbol     TEXT NOT NULL,
    side       TEXT NOT NULL,
    quantity   TEXT NOT NULL,
    price      TEXT,
    state      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source     TEXT
);
"""

_UPSERT = """
INSERT INTO trades (order_id, symbol, side, quantity, price, state, created_at, source)
VALUES (:order_id, :symbol, :side, :quantity, :price, :state, :created_at, :source)
ON CONFLICT(order_id) DO UPDATE SET
    state = excluded.state,
    price = excluded.price,
    quantity = excluded.quantity;
"""


class SqliteJournal:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> SqliteJournal:
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def record_trades(self, trades: list[TradeRecord]) -> int:
        rows = [
            {
                "order_id": t.order_id,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": str(t.quantity),
                "price": None if t.price is None else str(t.price),
                "state": t.state,
                "created_at": t.created_at,
                "source": t.source,
            }
            for t in trades
        ]
        self._conn.executemany(_UPSERT, rows)
        self._conn.commit()
        return len(rows)

    def recent_trades(self, limit: int = 50) -> list[TradeRecord]:
        cur = self._conn.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_row_to_trade(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


def _row_to_trade(row: sqlite3.Row) -> TradeRecord:
    return TradeRecord(
        order_id=row["order_id"],
        symbol=row["symbol"],
        side=row["side"],
        quantity=Decimal(row["quantity"]),
        price=None if row["price"] is None else Decimal(row["price"]),
        state=row["state"],
        created_at=row["created_at"],
        source=row["source"],
    )
