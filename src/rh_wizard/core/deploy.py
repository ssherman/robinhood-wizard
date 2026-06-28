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

from rh_wizard.allocation.engine import allocate, bucket_membership
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


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _dominant(reasons: list[str]) -> str:
    counts: dict[str, int] = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    # Most frequent reason; ties broken alphabetically for determinism.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def deployment_summary(
    report: AllocationReport,
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    vetted: VettedPlan,
) -> AllocationReport:
    member = bucket_membership(strategy, recommendation)
    investable = report.investable
    deployed_by_bucket: dict[str, Decimal] = {}
    for i in vetted.approved:
        if i.side != _BUY:
            continue
        b = member.get(_norm(i.symbol))
        if b is not None:
            deployed_by_bucket[b] = deployed_by_bucket.get(b, Decimal("0")) + _order_value(i)
    rejected_by_bucket: dict[str, list[str]] = {}
    for r in vetted.rejected:
        if r.intent.side != _BUY:
            continue
        b = member.get(_norm(r.intent.symbol))
        if b is not None:
            rejected_by_bucket.setdefault(b, []).append(r.reason)

    new_buckets = []
    notes = list(report.notes)
    for b in report.buckets:
        budget = (b.target_pct / 100 * investable) if investable > 0 else Decimal("0")
        deployed = deployed_by_bucket.get(b.bucket_id, Decimal("0"))
        cash_left = budget - deployed
        if cash_left < 0:
            cash_left = Decimal("0")
        new_buckets.append(
            b.model_copy(update={"budget": budget, "deployed": deployed, "cash_left": cash_left})
        )
        reasons = rejected_by_bucket.get(b.bucket_id, [])
        if cash_left > 0 and reasons:
            label = b.name or b.bucket_id
            notes.append(
                f"{label}: ${cash_left:.2f} left as cash — "
                f"{len(reasons)} name(s) rejected ({_dominant(reasons)})"
            )
    return report.model_copy(update={"buckets": new_buckets, "notes": notes})


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
    report = deployment_summary(report, strategy, recommendation, vetted)
    return plan, report, vetted
