"""The signal taxonomy (spec §3/§11): the named facts a strategy can request and a data
source can provide.

Phase 3 implements the quantitative Robinhood signals (quotes + fundamentals).
``HISTORICALS``/``EARNINGS`` and ``NEWS``/``SENTIMENT`` are declared seams — not provided
in Phase 3. NEWS/SENTIMENT are supplied by the Phase 4 research agent's own web tools
(not a batch DataSource); HISTORICALS/EARNINGS by a later Robinhood or external source.
"""

from __future__ import annotations

from enum import StrEnum


class Signal(StrEnum):
    # --- implemented in Phase 3 (Robinhood quotes + fundamentals) ---
    PRICE = "price"
    AVERAGE_VOLUME = "average_volume"
    MARKET_CAP = "market_cap"
    PE_RATIO = "pe_ratio"
    PB_RATIO = "pb_ratio"
    SECTOR = "sector"
    INDUSTRY = "industry"
    WEEK_52_HIGH = "week_52_high"
    WEEK_52_LOW = "week_52_low"
    DIVIDEND_YIELD = "dividend_yield"
    # --- declared seams (not provided in Phase 3) ---
    HISTORICALS = "historicals"
    EARNINGS = "earnings"
    NEWS = "news"
    SENTIMENT = "sentiment"


# The signals the risk engine's SymbolRisk requires (spec §9 liquidity floor + slippage).
RISK_SIGNALS: frozenset[Signal] = frozenset(
    {Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP}
)
