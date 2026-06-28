"""Allocation models (Phase 4e).

``AllocationRecommendation`` is the LLM structured-output target for the bucket recommender:
per bucket, the selected positions each with a *relative* weight (the only quantitative thing
the LLM emits — code normalizes and does all dollar/share math). It deliberately carries no
dollars or share counts. ``AllocationReport`` is the deterministic Allocator's audit output
(per-bucket target/current/drift/action) for render + journal; it is not an LLM target, so it
uses plain ``Decimal``.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic

from rh_wizard.models._types import LlmDecimal
from rh_wizard.models.research import Source


class RecommendedPosition(pydantic.BaseModel):
    symbol: str
    weight: LlmDecimal | None = None  # relative weight within the bucket; code normalizes
    thesis: str = ""


class BucketRecommendation(pydantic.BaseModel):
    bucket_id: str
    positions: list[RecommendedPosition] = []


class AllocationRecommendation(pydantic.BaseModel):
    buckets: list[BucketRecommendation] = []
    summary: str = ""
    sources: list[Source] = []  # web-search citations (attached by the recommender)


class BucketAllocation(pydantic.BaseModel):
    bucket_id: str
    name: str = ""
    target_pct: Decimal
    current_pct: Decimal
    drift_pct: Decimal
    within_band: bool
    # "buy" | "sell" | "hold (overweight, buy_only)" | "skipped (within band)" | "no candidates"
    action: str
    budget: Decimal = Decimal("0")  # target dollars for this bucket (target_pct × investable)
    deployed: Decimal = Decimal("0")  # approved-buy dollars mapped to this bucket
    cash_left: Decimal = Decimal("0")  # budget − deployed, floored at 0


class AllocationReport(pydantic.BaseModel):
    buckets: list[BucketAllocation] = []
    orphans: list[str] = []  # held symbols mapped to no bucket (left untouched)
    investable: Decimal = Decimal("0")
    notes: list[str] = []
