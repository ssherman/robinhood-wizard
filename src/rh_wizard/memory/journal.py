"""SQLite-backed trade journal (spec §6).

Stores one row per known broker order, keyed by order_id (idempotent upsert). Decimal
fields are stored as TEXT to avoid float precision loss.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from rh_wizard.models.allocation import AllocationRecommendation, AllocationReport
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.discovery import DiscoveryResult
from rh_wizard.models.order import OrderResult
from rh_wizard.models.plan import TradeIntent, VettedPlan
from rh_wizard.models.research import ResearchReport
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
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    mode        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS plan_intents (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    bucket      TEXT NOT NULL,
    side        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    quantity    TEXT,
    amount      TEXT,
    limit_price TEXT,
    rationale   TEXT,
    reason      TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS research_sources (
    run_id TEXT NOT NULL,
    seq    INTEGER NOT NULL,
    title  TEXT,
    url    TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS discovered_universe (
    run_id    TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    symbol    TEXT NOT NULL,
    rationale TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS discovery_sources (
    run_id TEXT NOT NULL,
    seq    INTEGER NOT NULL,
    title  TEXT,
    url    TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS allocation_report (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    bucket_id   TEXT NOT NULL,
    name        TEXT,
    target_pct  TEXT NOT NULL,
    current_pct TEXT NOT NULL,
    drift_pct   TEXT NOT NULL,
    within_band INTEGER NOT NULL,
    action      TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS recommendation_sources (
    run_id TEXT NOT NULL,
    seq    INTEGER NOT NULL,
    title  TEXT,
    url    TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS orders (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    status      TEXT NOT NULL,
    order_type  TEXT,
    quantity    TEXT,
    amount      TEXT,
    limit_price TEXT,
    order_id    TEXT,
    ref_id      TEXT,
    PRIMARY KEY (run_id, seq)
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

    def record_run(self, run: CycleRun) -> None:
        self._conn.execute(
            """
            INSERT INTO runs (run_id, strategy_id, mode, started_at, finished_at, status, note)
            VALUES (:run_id, :strategy_id, :mode, :started_at, :finished_at, :status, :note)
            ON CONFLICT(run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                note = excluded.note;
            """,
            {
                "run_id": run.run_id,
                "strategy_id": run.strategy_id,
                "mode": run.mode,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "status": run.status,
                "note": run.note,
            },
        )
        self._conn.commit()

    def record_plan(self, run_id: str, vetted: VettedPlan) -> None:
        self._conn.execute("DELETE FROM plan_intents WHERE run_id = ?", (run_id,))
        rows = []
        seq = 0
        for intent in vetted.approved:
            rows.append(_intent_row(run_id, seq, "approved", intent, None))
            seq += 1
        for rejected in vetted.rejected:
            rows.append(_intent_row(run_id, seq, "rejected", rejected.intent, rejected.reason))
            seq += 1
        if rows:
            self._conn.executemany(
                """
                INSERT INTO plan_intents
                    (run_id, seq, bucket, side, symbol, quantity, amount, limit_price,
                     rationale, reason)
                VALUES
                    (:run_id, :seq, :bucket, :side, :symbol, :quantity, :amount, :limit_price,
                     :rationale, :reason);
                """,
                rows,
            )
        self._conn.commit()

    def record_research(self, run_id: str, report: ResearchReport) -> None:
        self._conn.execute("DELETE FROM research_sources WHERE run_id = ?", (run_id,))
        rows = [
            {"run_id": run_id, "seq": i, "title": s.title, "url": s.url}
            for i, s in enumerate(report.sources)
        ]
        if rows:
            self._conn.executemany(
                """
                INSERT INTO research_sources (run_id, seq, title, url)
                VALUES (:run_id, :seq, :title, :url);
                """,
                rows,
            )
        self._conn.commit()

    def research_sources(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM research_sources WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    def record_discovery(self, run_id: str, result: DiscoveryResult) -> None:
        self._conn.execute("DELETE FROM discovered_universe WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM discovery_sources WHERE run_id = ?", (run_id,))
        trows = [
            {"run_id": run_id, "seq": i, "symbol": t.symbol, "rationale": t.rationale}
            for i, t in enumerate(result.tickers)
        ]
        if trows:
            self._conn.executemany(
                "INSERT INTO discovered_universe (run_id, seq, symbol, rationale) "
                "VALUES (:run_id, :seq, :symbol, :rationale);",
                trows,
            )
        srows = [
            {"run_id": run_id, "seq": i, "title": s.title, "url": s.url}
            for i, s in enumerate(result.sources)
        ]
        if srows:
            self._conn.executemany(
                "INSERT INTO discovery_sources (run_id, seq, title, url) "
                "VALUES (:run_id, :seq, :title, :url);",
                srows,
            )
        self._conn.commit()

    def discovered_universe(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM discovered_universe WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    def discovery_sources(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM discovery_sources WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    def record_allocation(
        self, run_id: str, report: AllocationReport, recommendation: AllocationRecommendation
    ) -> None:
        self._conn.execute("DELETE FROM allocation_report WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM recommendation_sources WHERE run_id = ?", (run_id,))
        brows = [
            {
                "run_id": run_id,
                "seq": i,
                "bucket_id": b.bucket_id,
                "name": b.name,
                "target_pct": str(b.target_pct),
                "current_pct": str(b.current_pct),
                "drift_pct": str(b.drift_pct),
                "within_band": 1 if b.within_band else 0,
                "action": b.action,
            }
            for i, b in enumerate(report.buckets)
        ]
        if brows:
            self._conn.executemany(
                "INSERT INTO allocation_report (run_id, seq, bucket_id, name, target_pct, "
                "current_pct, drift_pct, within_band, action) VALUES (:run_id, :seq, :bucket_id, "
                ":name, :target_pct, :current_pct, :drift_pct, :within_band, :action);",
                brows,
            )
        srows = [
            {"run_id": run_id, "seq": i, "title": s.title, "url": s.url}
            for i, s in enumerate(recommendation.sources)
        ]
        if srows:
            self._conn.executemany(
                "INSERT INTO recommendation_sources (run_id, seq, title, url) "
                "VALUES (:run_id, :seq, :title, :url);",
                srows,
            )
        self._conn.commit()

    def allocation_report(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM allocation_report WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    def recommendation_sources(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM recommendation_sources WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    def record_orders(self, run_id: str, orders: list[OrderResult]) -> None:
        self._conn.execute("DELETE FROM orders WHERE run_id = ?", (run_id,))
        rows = [
            {
                "run_id": run_id,
                "seq": i,
                "symbol": o.symbol,
                "side": o.side,
                "status": o.status,
                "order_type": o.order_type,
                "quantity": None if o.quantity is None else str(o.quantity),
                "amount": None if o.amount is None else str(o.amount),
                "limit_price": None if o.limit_price is None else str(o.limit_price),
                "order_id": o.order_id,
                "ref_id": o.ref_id,
            }
            for i, o in enumerate(orders)
        ]
        if rows:
            self._conn.executemany(
                "INSERT INTO orders (run_id, seq, symbol, side, status, order_type, quantity, "
                "amount, limit_price, order_id, ref_id) VALUES (:run_id, :seq, :symbol, :side, "
                ":status, :order_type, :quantity, :amount, :limit_price, :order_id, :ref_id);",
                rows,
            )
        self._conn.commit()

    def orders(self, run_id: str) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM orders WHERE run_id = ? ORDER BY seq", (run_id,))
        return [dict(row) for row in cur.fetchall()]

    def recent_runs(self, limit: int = 50) -> list[CycleRun]:
        cur = self._conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [
            CycleRun(
                run_id=row["run_id"],
                strategy_id=row["strategy_id"],
                mode=row["mode"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=row["status"],
                note=row["note"] or "",
            )
            for row in cur.fetchall()
        ]

    def plan_intents(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM plan_intents WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

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


def _intent_row(
    run_id: str, seq: int, bucket: str, intent: TradeIntent, reason: str | None
) -> dict:
    return {
        "run_id": run_id,
        "seq": seq,
        "bucket": bucket,
        "side": intent.side,
        "symbol": intent.symbol,
        "quantity": None if intent.quantity is None else str(intent.quantity),
        "amount": None if intent.amount is None else str(intent.amount),
        "limit_price": None if intent.limit_price is None else str(intent.limit_price),
        "rationale": intent.rationale,
        "reason": reason,
    }
