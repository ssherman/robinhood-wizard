"""Order execution models (Phase 5). ``ReviewResult`` is what the executor returns from
``review_equity_order`` (estimated cost + pre-trade alerts; ``ok`` is False when a blocking
alert is present). ``OrderResult`` is the outcome of trying to execute one intent —
``status`` is "placed", "skipped" (a blocking review alert), or "failed" (the place call
errored). These are deterministic records, not LLM outputs, so plain ``Decimal``.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class ReviewResult(pydantic.BaseModel):
    ok: bool
    estimated_cost: Decimal | None = None
    alerts: list[str] = []
    raw: dict = {}


class OrderResult(pydantic.BaseModel):
    symbol: str
    side: str
    status: str  # "placed" | "skipped" | "failed"
    order_type: str = ""  # "limit" | "market"; "" when never placed (skipped)
    quantity: Decimal | None = None
    amount: Decimal | None = None
    limit_price: Decimal | None = None
    order_id: str | None = None
    ref_id: str = ""
    raw: dict = {}
