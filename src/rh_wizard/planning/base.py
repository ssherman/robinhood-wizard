"""The plan seam (spec §5). A Planner turns a ResearchReport (+ portfolio + market) into a
proposed TradePlan that must still survive the risk engine. The Phase 4b LLM generator and
the Phase 4a deterministic stub both implement this Protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class Planner(Protocol):
    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan: ...
