"""Robinhood-backed order executor (Phase 5). Maps a vetted ``TradeIntent`` to MCP order
params and calls the typed broker wrappers. Whole-share intents become price-protected LIMIT
orders; fractional/notional intents become MARKET orders (Robinhood has no fractional limit
order). Imports the typed broker only — no LLM/strands. Real response shapes are parsed
defensively and live-verified (spec §18).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rh_wizard.models.order import OrderResult, ReviewResult
from rh_wizard.models.plan import TradeIntent


def _order_params(intent: TradeIntent) -> tuple[str, dict]:
    """(order_type, sizing-params) for an intent. Fractional/notional → market; whole → limit."""
    if intent.amount is not None:  # fractional buy: notional market order
        return "market", {"dollar_amount": str(intent.amount)}
    if intent.quantity is not None and intent.quantity != intent.quantity.to_integral_value():
        return "market", {"quantity": str(intent.quantity)}  # fractional sell: market
    if intent.quantity is not None and intent.limit_price is not None:
        return "limit", {"quantity": str(intent.quantity), "limit_price": str(intent.limit_price)}
    raise ValueError(f"cannot size order for {intent.symbol}: need amount, or quantity+limit_price")


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _unwrap(raw: dict) -> dict:
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def _parse_alerts(raw: dict) -> list[str]:
    alerts = _unwrap(raw).get("alerts")
    if not alerts:
        return []
    return [a if isinstance(a, str) else str(a) for a in alerts]


def _parse_order_id(raw: dict) -> str | None:
    d = _unwrap(raw)
    val = d.get("id") or d.get("order_id")
    return str(val) if val else None


class RobinhoodOrderExecutor:
    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def review(self, intent: TradeIntent, account: str) -> ReviewResult:
        try:
            order_type, params = _order_params(intent)
            raw = self._broker.review_equity_order(
                account, intent.symbol, intent.side, order_type, **params
            )
        except Exception as exc:  # a review that errors is a blocking condition → skip
            return ReviewResult(ok=False, alerts=[f"review failed: {exc}"], raw={})
        alerts = _parse_alerts(raw)
        cost = _to_decimal(_unwrap(raw).get("estimated_cost"))
        return ReviewResult(ok=not alerts, estimated_cost=cost, alerts=alerts, raw=raw)

    def place(self, intent: TradeIntent, account: str, ref_id: str) -> OrderResult:
        try:
            order_type, params = _order_params(intent)
            raw = self._broker.place_equity_order(
                account, intent.symbol, intent.side, order_type, ref_id=ref_id, **params
            )
        except Exception as exc:  # never raise into the cycle; return a failed result
            return OrderResult(
                symbol=intent.symbol,
                side=intent.side,
                status="failed",
                order_type="",
                quantity=intent.quantity,
                amount=intent.amount,
                limit_price=intent.limit_price,
                ref_id=ref_id,
                raw={"error": str(exc)},
            )
        return OrderResult(
            symbol=intent.symbol,
            side=intent.side,
            status="placed",
            order_type=order_type,
            quantity=intent.quantity,
            amount=intent.amount,
            limit_price=intent.limit_price,
            order_id=_parse_order_id(raw),
            ref_id=ref_id,
            raw=raw,
        )
