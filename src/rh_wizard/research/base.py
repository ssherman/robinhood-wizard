"""The research seam (spec §5). A Researcher investigates a strategy's universe against the
resolved MarketContext and returns a structured ResearchReport. It cannot place orders. The
Phase 4b LLM agent and the Phase 4a deterministic stub both implement this Protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class Researcher(Protocol):
    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport: ...
