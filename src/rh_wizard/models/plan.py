"""Trade plan + vetting models (spec §7).

A ``TradePlan`` is the LLM's proposed output (ordered ``TradeIntent``s). The risk engine
turns it into a ``VettedPlan`` (approved / rejected, with reasons). ``adjusted`` is a
forward-seam for future auto-resizing — empty in Phase 2.
"""

from __future__ import annotations

import pydantic

from rh_wizard.models._types import LlmDecimal


class TradeIntent(pydantic.BaseModel):
    side: str  # "buy" | "sell"
    symbol: str
    quantity: LlmDecimal | None = None  # target share quantity (or use ``amount``)
    amount: LlmDecimal | None = None  # target dollar amount (alternative to ``quantity``)
    limit_price: LlmDecimal | None = None
    rationale: str = ""
    confidence: LlmDecimal | None = None

    @pydantic.field_validator("side", mode="before")
    @classmethod
    def _normalize_side(cls, value: object) -> object:
        # LLMs emit "BUY"/"Sell"; canonicalize so the risk engine and journal see "buy"/"sell".
        return value.strip().lower() if isinstance(value, str) else value


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
