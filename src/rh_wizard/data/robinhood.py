# src/rh_wizard/data/robinhood.py
"""Robinhood as a DataSource (spec §11).

Quotes supply ``PRICE``; fundamentals supply ``AVERAGE_VOLUME`` / ``MARKET_CAP`` /
``PE_RATIO`` / ``PB_RATIO`` / ``SECTOR`` / ``INDUSTRY`` / 52-week range / ``DIVIDEND_YIELD``.
Wraps the typed ``BrokerClient``. Fundamentals field names were confirmed live against the
real payload (spec §18).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal

_PROVIDED: frozenset[Signal] = frozenset(
    {
        Signal.PRICE,
        Signal.AVERAGE_VOLUME,
        Signal.MARKET_CAP,
        Signal.PE_RATIO,
        Signal.PB_RATIO,
        Signal.SECTOR,
        Signal.INDUSTRY,
        Signal.WEEK_52_HIGH,
        Signal.WEEK_52_LOW,
        Signal.DIVIDEND_YIELD,
        Signal.FRACTIONABLE,
    }
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _first(raw: dict, *keys: str) -> Any:
    for k in keys:
        v = raw.get(k)
        if v not in (None, ""):
            return v
    return None


def _quote_price(quote: dict) -> Decimal | None:
    # Re-defined here to keep data/ decoupled from memory/ (different responsibility).
    for key in ("last_trade_price", "price", "last_price", "mark_price"):
        v = quote.get(key)
        if v not in (None, ""):
            return _to_decimal(v)
    return None


def _parse_fundamentals(raw: dict) -> dict[str, Any]:
    """Map a Robinhood fundamentals row to SymbolData fields.

    Field names confirmed live against the real ``get_equity_fundamentals`` payload
    (spec §18, 2026-06-23). A missing key degrades to ``None`` (a per-symbol gap).
    """
    return {
        "average_volume": _to_decimal(_first(raw, "average_volume")),
        "market_cap": _to_decimal(_first(raw, "market_cap")),
        "pe_ratio": _to_decimal(_first(raw, "pe_ratio")),
        "pb_ratio": _to_decimal(_first(raw, "pb_ratio")),
        "sector": _first(raw, "sector"),
        "industry": _first(raw, "industry"),
        "week_52_high": _to_decimal(_first(raw, "high_52_weeks")),
        "week_52_low": _to_decimal(_first(raw, "low_52_weeks")),
        "dividend_yield": _to_decimal(_first(raw, "dividend_yield")),
    }


def _parse_fractionable(raw: dict) -> bool | None:
    """Map a Robinhood tradability row to the fractionable flag. Unknown ⇒ None (safe)."""
    val = _first(raw, "fractional_tradability", "tradeable_fractional", "fractional")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("tradable", "tradeable", "true", "yes")
    return None


class RobinhoodDataSource:
    name = "robinhood"

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def provides(self) -> set[Signal]:
        return set(_PROVIDED)

    def fetch(self, symbols: list[str], signals: set[Signal]) -> dict[str, SymbolData]:
        wanted = signals & _PROVIDED
        if not symbols or not wanted:
            return {}
        fields: dict[str, dict[str, Any]] = {sym: {} for sym in symbols}

        if Signal.PRICE in wanted:
            for q in self._broker.get_equity_quotes(symbols):
                sym = q.get("symbol")
                if sym in fields:
                    fields[sym]["price"] = _quote_price(q)

        # Any non-price, non-fractionable provided signal is sourced from the fundamentals call.
        if wanted - {Signal.PRICE, Signal.FRACTIONABLE}:
            for row in self._broker.get_equity_fundamentals(symbols):
                sym = row.get("symbol")
                if sym in fields:
                    fields[sym].update(_parse_fundamentals(row))

        if Signal.FRACTIONABLE in wanted:
            for row in self._broker.get_equity_tradability(symbols):
                sym = row.get("symbol")
                if sym in fields:
                    fields[sym]["fractionable"] = _parse_fractionable(row)

        return {sym: SymbolData(symbol=sym, **vals) for sym, vals in fields.items()}
