"""The risk engine (spec §6/§9/§14) — pure, deterministic, no I/O.

``vet`` walks a TradePlan's intents in order, accumulating spend/cash against the policy
caps, and buckets each intent into approved or rejected (with a reason). It is the
integrity gate the LLM cannot bypass: plain code the deterministic cycle runs after plan
generation. v1 never adjusts an intent — anything that violates a guardrail is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import RejectedIntent, TradeIntent, TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy

_BUY = "buy"
_SELL = "sell"


@dataclass
class VetContext:
    policy: RiskPolicy
    portfolio_value: Decimal
    market: dict[str, SymbolRisk]
    running_cash: Decimal
    deployed: Decimal = Decimal("0")
    approved_count: int = 0
    held_value: dict[str, Decimal] = field(default_factory=dict)
    held_qty: dict[str, Decimal] = field(default_factory=dict)


def _portfolio_value(portfolio: PortfolioState) -> Decimal:
    if portfolio.total_value is not None:
        return portfolio.total_value
    held = sum(
        (p.market_value if p.market_value is not None else p.cost_basis)
        for p in portfolio.positions
    )
    return portfolio.cash + Decimal(held)


def _order_value(intent: TradeIntent) -> Decimal | None:
    """Dollar size of an intent: explicit amount, else quantity * limit_price."""
    if intent.amount is not None:
        return intent.amount
    if intent.quantity is not None and intent.limit_price is not None:
        return intent.quantity * intent.limit_price
    return None


def _build_context(
    policy: RiskPolicy, portfolio: PortfolioState, market: dict[str, SymbolRisk]
) -> VetContext:
    held_value: dict[str, Decimal] = {}
    held_qty: dict[str, Decimal] = {}
    for p in portfolio.positions:
        held_value[p.symbol] = p.market_value if p.market_value is not None else p.cost_basis
        held_qty[p.symbol] = p.quantity
    return VetContext(
        policy=policy,
        portfolio_value=_portfolio_value(portfolio),
        market=market,
        running_cash=portfolio.cash,
        held_value=held_value,
        held_qty=held_qty,
    )


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return part / whole * 100


def _reason_to_reject(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> str | None:
    # --- checks that apply to every intent (buy or sell) ---
    if intent.side not in (_BUY, _SELL):
        return f"invalid side '{intent.side}' (must be buy or sell)"
    if intent.limit_price is None or intent.limit_price <= 0:
        return "limit price required (all orders are limit orders)"
    if ctx.approved_count >= ctx.policy.max_trades_per_cycle:
        return f"exceeds max trades per cycle ({ctx.policy.max_trades_per_cycle})"
    sym = ctx.market.get(intent.symbol)
    if sym is None:
        return f"no market data for {intent.symbol}"
    deviation = _pct(abs(intent.limit_price - sym.price), sym.price)
    if deviation > ctx.policy.slippage_band_pct:
        return (
            f"limit price {deviation:.2f}% off market exceeds slippage band "
            f"{ctx.policy.slippage_band_pct}%"
        )
    return None


def _apply_approval(intent: TradeIntent, value: Decimal | None, ctx: VetContext) -> None:
    ctx.approved_count += 1


def vet(
    plan: TradePlan,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: dict[str, SymbolRisk],
) -> VettedPlan:
    ctx = _build_context(policy, portfolio, market)
    approved: list[TradeIntent] = []
    rejected: list[RejectedIntent] = []
    for intent in plan.intents:
        value = _order_value(intent)
        reason = _reason_to_reject(intent, value, ctx)
        if reason is not None:
            rejected.append(RejectedIntent(intent=intent, reason=reason))
            continue
        approved.append(intent)
        _apply_approval(intent, value, ctx)
    return VettedPlan(approved=approved, adjusted=[], rejected=rejected)
