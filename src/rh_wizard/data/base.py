"""The pluggable data-source seam (spec §3/§5/§6).

A source declares the signals it can supply (``provides``) and fetches them for a set of
symbols (``fetch``). Robinhood is the only v1 source; EDGAR / AlphaVantage (and any future
structured source) implement this same Protocol. News/sentiment is NOT a DataSource — the
Phase 4 research agent supplies it via its own web tools.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


@runtime_checkable
class DataSource(Protocol):
    name: str

    def provides(self) -> set[Signal]:
        """The signals this source can supply."""
        ...

    def fetch(self, symbols: list[str], signals: set[Signal]) -> dict[str, SymbolData]:
        """Fetch the requested (already ``provides() ∩ needed``) signals for ``symbols``.

        Returns a per-symbol ``SymbolData`` (absent facts left as ``None``). May raise on
        I/O failure — the resolver catches it and degrades.
        """
        ...
