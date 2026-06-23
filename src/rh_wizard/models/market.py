"""Per-symbol market facts the risk engine needs (spec §11).

A pure value object passed into the risk engine so it can check the liquidity floor and
slippage band without doing any I/O. Phase 3's data layer will populate these.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic

from rh_wizard.models.signals import Signal


class SymbolRisk(pydantic.BaseModel):
    symbol: str
    price: Decimal  # current/last market price
    average_volume: Decimal | None = None  # average daily share volume
    market_cap: Decimal | None = None


class SymbolData(pydantic.BaseModel):
    """Resolved per-symbol facts merged from one or more DataSources (spec §11).

    Every field except ``symbol`` is optional — the resolver degrades and reports, so an
    absent fact is a ``None`` field (a per-symbol gap), not an error.
    """

    symbol: str
    price: Decimal | None = None
    average_volume: Decimal | None = None
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    sector: str | None = None
    industry: str | None = None
    week_52_high: Decimal | None = None
    week_52_low: Decimal | None = None
    dividend_yield: Decimal | None = None


class MarketContext(pydantic.BaseModel):
    """Resolved market data for a candidate universe (spec §7).

    Records what was requested, what each symbol resolved to, which needed signals no
    source could provide (``unmet_signals``), and any per-source fetch errors (``notes``),
    so the Phase 4 cycle can decide whether to proceed. The resolver itself never aborts.
    """

    requested: list[Signal] = []
    symbols: dict[str, SymbolData] = {}
    unmet_signals: list[Signal] = []  # needed but no source provides them
    notes: list[str] = []  # per-source fetch errors / partial-data notes

    def to_symbol_risk(self) -> dict[str, SymbolRisk]:
        """Bridge to the Phase 2 risk engine. Only symbols with a price become a
        ``SymbolRisk`` (its ``price`` is mandatory); volume/market-cap pass through."""
        out: dict[str, SymbolRisk] = {}
        for symbol, data in self.symbols.items():
            if data.price is None:
                continue
            out[symbol] = SymbolRisk(
                symbol=symbol,
                price=data.price,
                average_volume=data.average_volume,
                market_cap=data.market_cap,
            )
        return out
