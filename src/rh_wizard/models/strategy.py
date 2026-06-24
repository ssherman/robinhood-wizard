"""The strategy model (spec §7).

A ``Strategy`` is authored as structured YAML in ``~/.rh-wizard/strategies/``. ``intent`` is
free natural language (e.g. a thematic allocation) — stored now and handed to the research
stage; the NL→structured compiler and theme→ticker universe discovery come later. Phase 4a
acts only on the explicit ``universe`` list. ``risk_overrides`` is layered onto the global
defaults by the risk engine's ``build_effective_policy``.
"""

from __future__ import annotations

import pydantic

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
