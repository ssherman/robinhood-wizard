# src/rh_wizard/data/resolver.py
"""Route the signals a strategy needs to the sources that provide them, and merge the
results into a MarketContext (spec §11).

Always degrades and reports: a needed signal no source provides is recorded in
``unmet_signals``; a source whose ``fetch`` raises is recorded in ``notes``; a per-symbol
missing fact is just a ``None`` field. The resolver never raises — spec §13's "abort the
cycle" decision lives in the Phase 4 cycle, which inspects the returned MarketContext.
"""

from __future__ import annotations

from collections.abc import Sequence

from rh_wizard.data.base import DataSource
from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.signals import Signal


def _merge(base: SymbolData, incoming: SymbolData) -> SymbolData:
    """Overlay ``incoming``'s non-None facts onto ``base`` (later source wins a conflict)."""
    updates = {k: v for k, v in incoming.model_dump().items() if k != "symbol" and v is not None}
    return base.model_copy(update=updates) if updates else base


class SignalResolver:
    def __init__(self, sources: Sequence[DataSource]) -> None:
        self._sources = list(sources)

    def resolve(self, universe: list[str], needed: set[Signal]) -> MarketContext:
        symbols: dict[str, SymbolData] = {sym: SymbolData(symbol=sym) for sym in universe}
        notes: list[str] = []
        provided: set[Signal] = set()
        attempted: set[Signal] = set()

        for source in self._sources:
            covers = source.provides() & needed
            if not covers:
                continue
            attempted |= covers
            try:
                fetched = source.fetch(list(universe), covers)
            except Exception as exc:  # degrade-and-report; the cycle decides whether to abort
                notes.append(f"{source.name} fetch failed: {exc}")
                continue
            provided |= covers
            for sym, data in fetched.items():
                if sym in symbols:
                    symbols[sym] = _merge(symbols[sym], data)

        return MarketContext(
            requested=sorted(needed, key=lambda s: s.value),
            symbols=symbols,
            unmet_signals=sorted(needed - attempted, key=lambda s: s.value),
            notes=notes,
        )
