"""The bucket-recommender seam (Phase 4e). A recommender turns a bucketed strategy's resolved
candidates into per-bucket selected positions with *relative* weights — the LLM's judgment.
The deterministic Allocator (``allocation/engine.py``) does the dollar/share math afterward.
The cycle depends on this Protocol so it stays brain-agnostic and testable without an LLM.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.allocation import AllocationRecommendation
from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class BucketRecommender(Protocol):
    def recommend(
        self,
        strategy: Strategy,
        bucket_candidates: dict[str, list[str]],
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> AllocationRecommendation: ...
