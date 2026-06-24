"""Research stage output (spec §7). The agent (stub in Phase 4a) returns candidate tickers
with a thesis and conviction; the planner turns this into a TradePlan."""

from __future__ import annotations

import pydantic

from rh_wizard.models._types import LlmDecimal


class Candidate(pydantic.BaseModel):
    symbol: str
    thesis: str = ""
    conviction: LlmDecimal | None = None  # 0..1, optional


class ResearchReport(pydantic.BaseModel):
    candidates: list[Candidate] = []
    summary: str = ""
