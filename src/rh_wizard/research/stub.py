"""Deterministic stand-in for the Phase 4b research agent. Flags every universe symbol that
actually resolved in the MarketContext as a neutral candidate — enough to drive the cycle
end-to-end offline. NOT a research strategy."""

from __future__ import annotations

from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy


class StubResearcher:
    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport:
        candidates = [
            Candidate(symbol=sym, thesis="(stub) candidate from strategy universe")
            for sym in strategy.universe
            if sym in market.symbols
        ]
        return ResearchReport(
            candidates=candidates,
            summary=f"(stub) {len(candidates)} candidate(s) from strategy '{strategy.id}'",
        )
