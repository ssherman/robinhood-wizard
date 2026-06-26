"""Phase 4c compiler models. ``CompiledStrategy`` is the LLM structured-output target for
``wizard compile`` (plain prose -> structured strategy); it deliberately has **no risk
field**, so prose can never weaken guardrails. ``CompileResult`` is what the compiler returns
to the CLI: the assembled ``Strategy`` plus the per-ticker rationale and web-search citations
used for the human-review header written into the YAML.
"""

from __future__ import annotations

import pydantic

from rh_wizard.models._types import LlmDecimal
from rh_wizard.models.research import Source
from rh_wizard.models.signals import Signal
from rh_wizard.models.strategy import Strategy


class SuggestedTicker(pydantic.BaseModel):
    symbol: str
    rationale: str = ""


class CompiledBucket(pydantic.BaseModel):
    name: str
    target_pct: LlmDecimal  # target % of investable capital (schema-safe Decimal)
    intent: str = ""
    tickers: list[SuggestedTicker] = []


class CompiledStrategy(pydantic.BaseModel):
    name: str
    intent: str = ""
    tickers: list[SuggestedTicker] = []
    buckets: list[CompiledBucket] = []  # non-empty ⇒ a bucketed thematic allocation
    signals_needed: list[Signal] = []
    cadence: str | None = None


class CompileResult(pydantic.BaseModel):
    strategy: Strategy
    tickers: list[SuggestedTicker] = []
    buckets: list[CompiledBucket] = []  # per-bucket compiled tickers, for the review header
    sources: list[Source] = []
