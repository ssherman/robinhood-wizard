"""The allocation engine (Phase 4e) — pure, deterministic, no I/O.

``allocate`` turns the LLM's per-bucket relative-weight recommendation into a concretely sized
``TradePlan``: per-bucket budget = target% × investable capital, split across the bucket's
recommended positions by normalized weight, converted to shares under the fractional/whole-share
rules. A bucket whose drift is within ``rebalance_band_pct`` is skipped. The result still passes
through the risk ``vet()`` unchanged — the Allocator only sizes, it never bypasses a guardrail.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from rh_wizard.models.allocation import (
    AllocationRecommendation,
    AllocationReport,
    BucketAllocation,
    BucketRecommendation,
)
from rh_wizard.models.market import SymbolData
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskPolicy
from rh_wizard.models.strategy import Strategy

_BUY = "buy"
_SELL = "sell"


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _portfolio_value(portfolio: PortfolioState) -> Decimal:
    if portfolio.total_value is not None:
        return portfolio.total_value
    held = sum(
        (p.market_value if p.market_value is not None else p.cost_basis)
        for p in portfolio.positions
    )
    return portfolio.cash + Decimal(held)


def _held_value(portfolio: PortfolioState) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for p in portfolio.positions:
        sym = _norm(p.symbol)
        value = p.market_value if p.market_value is not None else p.cost_basis
        out[sym] = out.get(sym, Decimal("0")) + value
    return out


def bucket_membership(
    strategy: Strategy, recommendation: AllocationRecommendation
) -> dict[str, str]:
    """Map each candidate/recommended symbol to its bucket id (first match wins)."""
    rec_by_bucket = {r.bucket_id: r for r in recommendation.buckets}
    member: dict[str, str] = {}
    for bucket in strategy.buckets:
        rec = rec_by_bucket.get(bucket.id)
        symbols = [p.symbol for p in rec.positions] if rec else []
        symbols += list(bucket.universe)
        for sym in symbols:
            member.setdefault(_norm(sym), bucket.id)
    return member


def _buy_intent(
    symbol: str,
    dollars: Decimal,
    data: SymbolData,
    allow_fractional: bool,
    rationale: str = "",
) -> TradeIntent | None:
    price = data.price
    if price is None or price <= 0 or dollars <= 0:
        return None
    fractional = allow_fractional and bool(data.fractionable)
    if fractional:
        return TradeIntent(
            side=_BUY, symbol=symbol, amount=dollars, limit_price=price, rationale=rationale
        )
    qty = (dollars / price).to_integral_value(rounding=ROUND_DOWN)
    if qty <= 0:
        return None
    return TradeIntent(
        side=_BUY, symbol=symbol, quantity=qty, limit_price=price, rationale=rationale
    )


def _split_buys(
    rec: BucketRecommendation | None,
    shortfall: Decimal,
    market: dict[str, SymbolData],
    allow_fractional: bool,
    member: dict[str, str],
    bucket_id: str,
    exclude: frozenset[str],
) -> list[TradeIntent]:
    if rec is None or shortfall <= 0:
        return []
    exclude = frozenset(_norm(s) for s in exclude)
    priced = [
        p
        for p in rec.positions
        if _norm(p.symbol) in market
        and market[_norm(p.symbol)].price
        and member.get(_norm(p.symbol)) == bucket_id
        and _norm(p.symbol) not in exclude
    ]
    if not priced:
        return []
    weights = [
        p.weight if (p.weight is not None and p.weight > 0) else Decimal("0") for p in priced
    ]
    total = sum(weights)
    if total <= 0:  # equal-weight fallback
        weights = [Decimal("1") for _ in priced]
        total = Decimal(len(priced))
    # Rank by weight desc, then symbol asc, so allocate() can interleave buckets fairly by rank.
    ranked = sorted(zip(priced, weights, strict=True), key=lambda pw: (-pw[1], _norm(pw[0].symbol)))
    intents: list[TradeIntent] = []
    for pos, w in ranked:
        sym = _norm(pos.symbol)
        dollars = shortfall * w / total
        intent = _buy_intent(sym, dollars, market[sym], allow_fractional, rationale=pos.thesis)
        if intent is not None:
            intents.append(intent)
    return intents


def _trim_sells(
    bucket_id: str,
    member: dict[str, str],
    held_value: dict[str, Decimal],
    excess: Decimal,
    market: dict[str, SymbolData],
    allow_fractional: bool,
) -> list[TradeIntent]:
    if excess <= 0:
        return []
    in_bucket = {sym: v for sym, v in held_value.items() if member.get(sym) == bucket_id}
    total = sum(in_bucket.values(), Decimal("0"))
    if total <= 0:
        return []
    intents: list[TradeIntent] = []
    for sym, value in in_bucket.items():
        data = market.get(sym)
        if data is None or data.price is None or data.price <= 0:
            continue
        dollars = excess * value / total
        if dollars <= 0:
            continue
        if allow_fractional and bool(data.fractionable):
            qty = dollars / data.price
        else:
            qty = (dollars / data.price).to_integral_value(rounding=ROUND_DOWN)
        if qty <= 0:
            continue
        intents.append(
            TradeIntent(
                side=_SELL,
                symbol=sym,
                quantity=qty,
                limit_price=data.price,
                rationale="trim to bucket target",
            )
        )
    return intents


def _interleave(bucket_buys: list[list[TradeIntent]]) -> list[TradeIntent]:
    """Round-robin across buckets by rank so a binding cap is shared fairly, not consumed
    bucket-by-bucket (which starves late buckets). Each inner list is one bucket's buys,
    already ordered by rank (weight desc, symbol asc)."""
    out: list[TradeIntent] = []
    if not bucket_buys:
        return out
    depth = max(len(b) for b in bucket_buys)
    for rank in range(depth):
        for buys in bucket_buys:
            if rank < len(buys):
                out.append(buys[rank])
    return out


def allocate(
    strategy: Strategy,
    recommendation: AllocationRecommendation,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    market: dict[str, SymbolData],
    exclude: frozenset[str] = frozenset(),
) -> tuple[TradePlan, AllocationReport]:
    portfolio_value = _portfolio_value(portfolio)
    investable = portfolio_value * (1 - policy.cash_reserve_pct / 100)
    held_value = _held_value(portfolio)
    member = bucket_membership(strategy, recommendation)
    rec_by_bucket = {r.bucket_id: r for r in recommendation.buckets}

    bucket_buys: list[list[TradeIntent]] = []
    sell_intents: list[TradeIntent] = []
    report_buckets: list[BucketAllocation] = []

    for bucket in strategy.buckets:
        budget = bucket.target_pct / 100 * investable
        current = sum(
            (v for sym, v in held_value.items() if member.get(sym) == bucket.id), Decimal("0")
        )
        current_pct = (current / investable * 100) if investable > 0 else Decimal("0")
        drift = current_pct - bucket.target_pct
        within_band = abs(drift) <= strategy.rebalance_band_pct
        action = "hold"
        if within_band:
            action = "skipped (within band)"
        elif drift < 0:  # underweight -> buy the shortfall
            buys = _split_buys(
                rec_by_bucket.get(bucket.id),
                budget - current,
                market,
                strategy.allow_fractional,
                member,
                bucket.id,
                exclude,
            )
            if buys:
                bucket_buys.append(buys)
                action = "buy"
            else:
                action = "no candidates"
        else:  # overweight -> sell to trim (full mode only)
            if strategy.rebalance_mode == "full":
                sells = _trim_sells(
                    bucket.id,
                    member,
                    held_value,
                    current - budget,
                    market,
                    strategy.allow_fractional,
                )
                if sells:
                    sell_intents.extend(sells)
                    action = "sell"
                else:
                    action = "hold (overweight, no sellable position)"
            else:
                action = "hold (overweight, buy_only)"
        report_buckets.append(
            BucketAllocation(
                bucket_id=bucket.id,
                name=bucket.name,
                target_pct=bucket.target_pct,
                current_pct=current_pct,
                drift_pct=drift,
                within_band=within_band,
                action=action,
            )
        )

    buy_intents = _interleave(bucket_buys)
    orphans = sorted(sym for sym in held_value if sym not in member)
    report = AllocationReport(buckets=report_buckets, orphans=orphans, investable=investable)
    return TradePlan(intents=sell_intents + buy_intents, rationale=recommendation.summary), report
