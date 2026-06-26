"""The strategy model (spec §7).

A ``Strategy`` is authored as structured YAML in ``~/.rh-wizard/strategies/``. ``intent`` is
free natural language (e.g. a thematic allocation) — stored now and handed to the research
stage; the NL→structured compiler and theme→ticker universe discovery come later. Phase 4a
acts only on the explicit ``universe`` list. ``risk_overrides`` is layered onto the global
defaults by the risk engine's ``build_effective_policy``.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic

from rh_wizard.models.bucket import Bucket
from rh_wizard.models.signals import Signal


class Strategy(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    id: str
    name: str
    intent: str = ""  # free-text thesis (used by the Phase 4b research agent)
    universe: list[str] = []  # explicit candidate tickers (Phase 4a)
    signals_needed: set[Signal] = set()  # signals the strategy wants resolved
    cadence: str | None = None  # hint only in v1 (e.g. "weekly")
    risk_overrides: dict[str, object] = {}  # merged onto global RiskPolicy defaults
    web_research: bool = True  # Phase 4b-2: use web search in the research stage
    discover: bool = False  # Phase 4d: discover candidate tickers from `intent` each cycle
    max_candidates: int = 20  # Phase 4d: cap on discovered candidates per cycle
    # --- Phase 4e: bucketed thematic-allocation strategies ---
    buckets: list[Bucket] = []  # non-empty ⇒ bucketed mode (mutually exclusive with the flat
    # universe/discover fields above)
    allow_fractional: bool = True  # size fractionally when the broker supports it for a symbol
    rebalance_mode: str = "full"  # "full" (buy + sell-to-trim) | "buy_only"
    rebalance_band_pct: Decimal = Decimal("5")  # drift tolerance before a bucket is traded

    @pydantic.model_validator(mode="after")
    def _validate_buckets(self) -> Strategy:
        if self.rebalance_mode not in ("full", "buy_only"):
            msg = f"rebalance_mode must be 'full' or 'buy_only', got {self.rebalance_mode!r}"
            raise ValueError(msg)
        if not self.buckets:
            return self
        if self.universe or self.discover:
            raise ValueError("buckets and the flat universe/discover fields are mutually exclusive")
        total = Decimal("0")
        for b in self.buckets:
            if b.target_pct <= 0:
                raise ValueError(f"bucket {b.id!r} target_pct must be > 0")
            total += b.target_pct
        if total > 100:
            raise ValueError(f"bucket target_pct sums to {total}, which exceeds 100")
        return self
