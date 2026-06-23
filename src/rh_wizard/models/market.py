"""Per-symbol market facts the risk engine needs (spec §11).

A pure value object passed into the risk engine so it can check the liquidity floor and
slippage band without doing any I/O. Phase 3's data layer will populate these.
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class SymbolRisk(pydantic.BaseModel):
    symbol: str
    price: Decimal  # current/last market price
    average_volume: Decimal | None = None  # average daily share volume
    market_cap: Decimal | None = None
