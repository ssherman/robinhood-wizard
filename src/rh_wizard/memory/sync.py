"""Sync the broker's equity order history into the journal (idempotent)."""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.models.trade import TradeRecord


def _order_price(raw: dict) -> Decimal | None:
    for key in ("average_price", "price", "last_trade_price"):
        value = raw.get(key)
        if value is not None:
            return Decimal(str(value))
    return None


def _to_trade_record(raw: dict) -> TradeRecord:
    return TradeRecord(
        order_id=str(raw.get("id") or raw.get("order_id") or ""),
        symbol=str(raw.get("symbol", "")),
        side=str(raw.get("side", "")),
        quantity=Decimal(str(raw.get("quantity", raw.get("shares", "0")))),
        price=_order_price(raw),
        state=str(raw.get("state", "")),
        created_at=str(raw.get("created_at", "")),
        source=raw.get("placed_agent") or raw.get("source"),
    )


def sync_equity_orders(
    broker, account_number: str, journal, *, created_at_gte: str | None = None
) -> int:
    raw_orders = broker.get_equity_orders(account_number, created_at_gte=created_at_gte)
    records = [_to_trade_record(o) for o in raw_orders]
    return journal.record_trades(records)
