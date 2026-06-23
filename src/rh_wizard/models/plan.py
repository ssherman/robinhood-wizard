"""Trade plan + vetting models (spec §7).

A ``TradePlan`` is the LLM's proposed output (ordered ``TradeIntent``s). The risk engine
turns it into a ``VettedPlan`` (approved / rejected, with reasons). ``adjusted`` is a
forward-seam for future auto-resizing — empty in Phase 2.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class TradeIntent(pydantic.BaseModel):
    side: str  # "buy" | "sell"
    symbol: str
    quantity: Decimal | None = None  # target share quantity (or use ``amount``)
    amount: Decimal | None = None  # target dollar amount (alternative to ``quantity``)
    limit_price: Decimal | None = None
    rationale: str = ""
    confidence: Decimal | None = None


class TradePlan(pydantic.BaseModel):
    intents: list[TradeIntent] = []
    rationale: str = ""


class RejectedIntent(pydantic.BaseModel):
    intent: TradeIntent
    reason: str


class VettedPlan(pydantic.BaseModel):
    approved: list[TradeIntent] = []
    adjusted: list[TradeIntent] = []  # forward-seam; always empty in Phase 2
    rejected: list[RejectedIntent] = []
