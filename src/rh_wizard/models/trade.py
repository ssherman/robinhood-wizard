"""Journal trade record (spec §6/§7). One row per known broker order."""

from __future__ import annotations

from decimal import Decimal

import pydantic


class TradeRecord(pydantic.BaseModel):
    order_id: str  # broker order id — idempotency key
    symbol: str
    side: str  # "buy" / "sell"
    quantity: Decimal
    price: Decimal | None  # avg fill price; None when not (yet) filled
    state: str  # filled / cancelled / rejected / ...
    created_at: str  # ISO timestamp from the broker
    source: str | None = None  # placed_agent: user / agentic / recurring / ...
