"""Research stage output (spec §7). The agent returns candidate tickers with a thesis and
conviction; Phase 4b-2 adds web-search source citations for the audit trail. The planner
turns this into a TradePlan."""

from __future__ import annotations

import pydantic

from rh_wizard.models._types import LlmDecimal


class Candidate(pydantic.BaseModel):
    symbol: str
    thesis: str = ""
    conviction: LlmDecimal | None = None  # 0..1, optional


class Source(pydantic.BaseModel):
    title: str = ""
    url: str = ""


class ResearchReport(pydantic.BaseModel):
    candidates: list[Candidate] = []
    summary: str = ""
    sources: list[Source] = []  # web-search citations (Phase 4b-2); empty for non-web research
