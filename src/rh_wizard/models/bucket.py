"""The allocation-bucket model (Phase 4e). A ``Bucket`` is a theme inside a bucketed strategy:
a target share of investable capital plus the inputs that drive its candidate universe
(an explicit ``universe`` and/or per-bucket ``discover``). The deterministic Allocator sizes
positions to hit ``target_pct``; the LLM recommender supplies relative weights within it.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class Bucket(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    id: str
    name: str = ""
    target_pct: Decimal  # share of investable capital (whole-number percent, e.g. 40 == 40%)
    intent: str = ""  # theme text driving this bucket's discovery + research
    universe: list[str] = []  # explicit tickers for this bucket (optional)
    discover: bool = False  # per-bucket universe discovery
    max_candidates: int = 20
