"""Compose the effective RiskPolicy: strategy overrides merged onto global defaults,
then clamped to an optional global hard-ceiling (spec §9).

Pure functions — no I/O, no config import. Callers pass the defaults/ceiling in.
"""

from __future__ import annotations

from collections.abc import Mapping

from rh_wizard.models.risk import RiskCeiling, RiskPolicy


def effective_policy(
    defaults: RiskPolicy, overrides: Mapping[str, object] | None = None
) -> RiskPolicy:
    """Layer ``overrides`` onto ``defaults``. Re-validates types and rejects unknown keys
    (RiskPolicy is ``extra="forbid"``)."""
    if not overrides:
        return defaults
    return RiskPolicy(**{**defaults.model_dump(), **dict(overrides)})


def apply_ceiling(policy: RiskPolicy, ceiling: RiskCeiling | None) -> RiskPolicy:
    """Clamp an effective policy to the global hard-ceiling so overrides can't weaken
    safety. ``None`` ceiling = disabled (return policy unchanged)."""
    if ceiling is None:
        return policy
    updates: dict[str, object] = {}

    # "max" dials: an override must not exceed the ceiling — clamp DOWN.
    if ceiling.max_position_pct is not None:
        updates["max_position_pct"] = min(policy.max_position_pct, ceiling.max_position_pct)
    if ceiling.max_trades_per_cycle is not None:
        updates["max_trades_per_cycle"] = min(
            policy.max_trades_per_cycle, ceiling.max_trades_per_cycle
        )
    if ceiling.max_deploy_pct_per_cycle is not None:
        updates["max_deploy_pct_per_cycle"] = min(
            policy.max_deploy_pct_per_cycle, ceiling.max_deploy_pct_per_cycle
        )
    if ceiling.max_slippage_band_pct is not None:
        updates["slippage_band_pct"] = min(policy.slippage_band_pct, ceiling.max_slippage_band_pct)
    if ceiling.max_drawdown_kill_switch_pct is not None:
        updates["drawdown_kill_switch_pct"] = min(
            policy.drawdown_kill_switch_pct, ceiling.max_drawdown_kill_switch_pct
        )

    # "min/floor" dials: an override must not go below the floor — clamp UP.
    if ceiling.min_cash_reserve_pct is not None:
        updates["cash_reserve_pct"] = max(policy.cash_reserve_pct, ceiling.min_cash_reserve_pct)
    if ceiling.min_price_floor is not None:
        updates["min_price"] = max(policy.min_price, ceiling.min_price_floor)
    if ceiling.min_avg_volume_floor is not None:
        updates["min_avg_volume"] = max(policy.min_avg_volume, ceiling.min_avg_volume_floor)
    if ceiling.min_market_cap_floor is not None:
        updates["min_market_cap"] = max(policy.min_market_cap, ceiling.min_market_cap_floor)

    return policy.model_copy(update=updates)


def build_effective_policy(
    defaults: RiskPolicy,
    ceiling: RiskCeiling | None = None,
    overrides: Mapping[str, object] | None = None,
) -> RiskPolicy:
    """Strategy overrides merged onto defaults, then clamped to the global hard-ceiling."""
    return apply_ceiling(effective_policy(defaults, overrides), ceiling)
