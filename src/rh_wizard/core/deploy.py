"""Deploy-completeness for bucketed allocation.

Spec: docs/.../2026-06-28-bucket-deploy-completeness.

``complete_allocation`` runs a bounded allocate <-> vet loop: it feeds vet's rejected buy symbols
back to the pure allocator as exclusions, so dollars freed by a rejected/floored name flow to the
surviving names in the same bucket. It returns the best-deploying round (never worse than round 0).
``vet`` stays the sole cap authority; ``allocate`` stays pure. This module composes them and is
itself pure and deterministic (no I/O, no llm).
"""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.allocation.engine import allocate
from rh_wizard.models.allocation import AllocationRecommendation, AllocationReport
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradeIntent, TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.models.strategy import Strategy
from rh_wizard.risk.engine import vet

_BUY = "buy"
_MAX_ROUNDS = 3


def _order_value(intent: TradeIntent) -> Decimal:
    if intent.amount is not None:
        return intent.amount
    if intent.quantity is not None and intent.limit_price is not None:
        return intent.quantity * intent.limit_price
    return Decimal("0")


def _deployed(vetted: VettedPlan) -> Decimal:
    return sum((_order_value(i) for i in vetted.approved if i.side == _BUY), Decimal("0"))


def complete_allocation(
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: MarketContext,
    max_rounds: int = _MAX_ROUNDS,
) -> tuple[TradePlan, AllocationReport, VettedPlan]:
    symbols = market.symbols
    risk = market.to_symbol_risk()
    excluded: set[str] = set()

    plan, report = allocate(strategy, recommendation, policy, portfolio, symbols)
    vetted = vet(plan, policy, portfolio, risk)
    best = (plan, report, vetted, _deployed(vetted))

    for _ in range(max_rounds):
        newly = {r.intent.symbol for r in vetted.rejected if r.intent.side == _BUY} - excluded
        if not newly:
            break
        excluded |= newly
        plan, report = allocate(
            strategy, recommendation, policy, portfolio, symbols, exclude=frozenset(excluded)
        )
        vetted = vet(plan, policy, portfolio, risk)
        deployed = _deployed(vetted)
        if deployed > best[3]:
            best = (plan, report, vetted, deployed)

    plan, report, vetted, _ = best
    return plan, report, vetted
