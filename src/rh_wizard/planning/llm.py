"""LLM-backed plan stage (spec §5). Replaces the Phase 4a stub behind the same ``Planner``
Protocol. It turns a ResearchReport into a proposed TradePlan that must still survive the
deterministic risk engine. The prompt constrains it toward limit orders at the current price.
"""

from __future__ import annotations

from rh_wizard.llm.base import StructuredLlm
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy

PLAN_SYSTEM = (
    "You translate research into a concrete TradePlan for a small, risk-managed account. "
    "Rules: propose LIMIT orders only; set each limit price AT the current market price "
    "shown (orders far from the market are rejected); prefer a few high-conviction positions "
    "over many; never propose selling a symbol that is not currently held. A deterministic "
    "risk engine independently vets every intent for position size, cash reserve, liquidity, "
    "and slippage and will reject anything unsafe — do not try to bypass it."
)


def _candidate_lines(report: ResearchReport, market: MarketContext) -> list[str]:
    lines = []
    for c in report.candidates:
        d = market.symbols.get(c.symbol)
        price = d.price if d is not None else None
        price_str = "unknown" if price is None else str(price)
        conv = "" if c.conviction is None else f", conviction={c.conviction}"
        lines.append(f"- {c.symbol}: price={price_str}{conv} — {c.thesis or '(no thesis)'}")
    return lines


def _plan_prompt(
    strategy: Strategy, report: ResearchReport, market: MarketContext, portfolio: PortfolioState
) -> str:
    held = {p.symbol for p in portfolio.positions}
    lines = [
        f"Strategy: {strategy.name}",
        f"Thesis: {strategy.intent or '(none)'}",
        f"Research summary: {report.summary or '(none)'}",
        "",
        "Researched candidates (use the price shown as the limit price):",
        *_candidate_lines(report, market),
        "",
        f"Currently held: {', '.join(sorted(held)) or '(none)'}",
        f"Cash available: {portfolio.cash}",
        "",
        "Return a TradePlan of TradeIntents (side, symbol, quantity, limit_price, rationale).",
    ]
    return "\n".join(lines)


class LlmPlanner:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan:
        prompt = _plan_prompt(strategy, report, market, portfolio)
        return self._llm.generate(TradePlan, prompt, system=PLAN_SYSTEM)
