"""LLM-backed research stage (spec §5). Replaces the Phase 4a stub behind the same
``Researcher`` Protocol. It investigates the strategy's universe against the resolved market
data and returns a structured ResearchReport; it cannot place orders.
"""

from __future__ import annotations

from rh_wizard.llm.base import StructuredLlm
from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy

RESEARCH_SYSTEM = (
    "You are a disciplined equity research analyst for a small, risk-managed account. "
    "Given a strategy thesis and current market data, identify which candidate tickers fit "
    "the thesis and assign each a brief rationale and a conviction from 0 to 1. Only use the "
    "data provided; do not invent prices or fundamentals. A deterministic risk engine will "
    "vet anything that is later proposed for trading — your job is research, not order sizing."
)


def _fmt_symbol(symbol: str, market: MarketContext) -> str:
    d = market.symbols.get(symbol)
    if d is None:
        return f"- {symbol}: (no market data resolved)"
    parts = []
    if d.price is not None:
        parts.append(f"price={d.price}")
    if d.pe_ratio is not None:
        parts.append(f"P/E={d.pe_ratio}")
    if d.market_cap is not None:
        parts.append(f"mktcap={d.market_cap}")
    if d.sector:
        parts.append(f"sector={d.sector}")
    if d.industry:
        parts.append(f"industry={d.industry}")
    if not parts:
        return f"- {symbol}: (no market data resolved)"
    return f"- {symbol}: " + ", ".join(parts)


def _research_prompt(strategy: Strategy, market: MarketContext, portfolio: PortfolioState) -> str:
    held = {p.symbol for p in portfolio.positions}
    lines = [
        f"Strategy: {strategy.name}",
        f"Thesis (free text): {strategy.intent or '(none provided)'}",
        "",
        "Candidate universe and resolved market data:",
        *[_fmt_symbol(s, market) for s in strategy.universe],
        "",
        f"Currently held: {', '.join(sorted(held)) or '(none)'}",
        f"Cash available: {portfolio.cash}",
    ]
    if market.unmet_signals:
        lines.append(
            "Unmet signals (data gaps): " + ", ".join(s.value for s in market.unmet_signals)
        )
    lines.append("")
    lines.append(
        "Return a ResearchReport: candidates that fit the thesis (with thesis text "
        "and conviction 0-1) plus a one-paragraph summary."
    )
    return "\n".join(lines)


class LlmResearcher:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport:
        prompt = _research_prompt(strategy, market, portfolio)
        return self._llm.generate(ResearchReport, prompt, system=RESEARCH_SYSTEM)
