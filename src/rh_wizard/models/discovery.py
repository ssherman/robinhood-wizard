"""Phase 4d universe-discovery models. ``DiscoveredUniverse`` is the LLM structured-output
target for the discovery stage (theme -> candidate tickers); ``DiscoveryResult`` is what the
discoverer returns to the cycle: the candidate tickers plus the web-search citations for the
audit trail. Reuses ``SuggestedTicker`` (symbol + one-line rationale) from the 4c models.
"""

from __future__ import annotations

import pydantic

from rh_wizard.models.compile import SuggestedTicker
from rh_wizard.models.research import Source


class DiscoveredUniverse(pydantic.BaseModel):
    tickers: list[SuggestedTicker] = []


class DiscoveryResult(pydantic.BaseModel):
    tickers: list[SuggestedTicker] = []
    sources: list[Source] = []
