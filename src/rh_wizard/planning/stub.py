"""Deterministic stand-in for the Phase 4b plan generator. Proposes a 1-share limit buy (at
the current market price, so it's within any slippage band) of each candidate not already
held and with a known price. Exercises the full risk/render/journal pipeline; NOT a trading
strategy."""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


class StubPlanner:
    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan:
        held = {p.symbol for p in portfolio.positions}
        intents: list[TradeIntent] = []
        for candidate in report.candidates:
            if candidate.symbol in held:
                continue
            data = market.symbols.get(candidate.symbol)
            if data is None or data.price is None:
                continue
            intents.append(
                TradeIntent(
                    side="buy",
                    symbol=candidate.symbol,
                    quantity=Decimal("1"),
                    limit_price=data.price,
                    rationale="(stub) 1-share probe buy",
                )
            )
        return TradePlan(intents=intents, rationale="(stub) deterministic plan")
