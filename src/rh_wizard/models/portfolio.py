"""Live portfolio models (spec §7). Money/quantities are Decimal."""

from __future__ import annotations

from decimal import Decimal

import pydantic


class Position(pydantic.BaseModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    # Enrichment (best-effort, from quotes) — None until enrich_with_quotes runs.
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pl: Decimal | None = None
    unrealized_pl_pct: Decimal | None = None


class PortfolioState(pydantic.BaseModel):
    account_number: str
    positions: list[Position]
    cash: Decimal
    buying_power: Decimal
    # Aggregate enrichment — None until enrich_with_quotes runs.
    market_value: Decimal | None = None
    total_value: Decimal | None = None
    total_return_pct: Decimal | None = None
