"""Risk guardrail models (spec §7/§9).

``RiskPolicy`` holds the per-strategy dials with conservative defaults tuned for a
~$3,000 account. ``RiskCeiling`` is the optional global hard-ceiling: it bounds what any
strategy override may set, so a typo can't (e.g.) push max-position to 100%.
Percentages are whole-number Decimals (``Decimal("20")`` == 20%).
"""

from __future__ import annotations

from decimal import Decimal

import pydantic


class RiskPolicy(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    max_position_pct: Decimal = Decimal("20")  # max % of portfolio value per position
    cash_reserve_pct: Decimal = Decimal("10")  # min % of portfolio kept as cash
    max_trades_per_cycle: int = 5
    max_deploy_pct_per_cycle: Decimal = Decimal("30")  # max % of portfolio bought per cycle
    slippage_band_pct: Decimal = Decimal("0.5")  # max |limit - market| / market, percent
    min_price: Decimal = Decimal("5")  # liquidity floor: min share price
    min_avg_volume: Decimal = Decimal("1000000")  # liquidity floor: min avg daily volume
    min_market_cap: Decimal = Decimal("1000000000")  # liquidity floor: min market cap
    drawdown_kill_switch_pct: Decimal = Decimal("15")  # halt threshold (enforced in Phase 6)


class RiskCeiling(pydantic.BaseModel):
    """Optional global bounds on an effective policy. Only set fields are clamped."""

    model_config = pydantic.ConfigDict(extra="forbid")

    max_position_pct: Decimal | None = None  # clamp policy.max_position_pct DOWN to this
    min_cash_reserve_pct: Decimal | None = None  # clamp policy.cash_reserve_pct UP to this
    max_trades_per_cycle: int | None = None
    max_deploy_pct_per_cycle: Decimal | None = None
    max_slippage_band_pct: Decimal | None = None
    min_price_floor: Decimal | None = None  # clamp policy.min_price UP to this
    min_avg_volume_floor: Decimal | None = None  # clamp policy.min_avg_volume UP
    min_market_cap_floor: Decimal | None = None  # clamp policy.min_market_cap UP
    max_drawdown_kill_switch_pct: Decimal | None = None  # clamp policy.drawdown DOWN
