from decimal import Decimal

import pydantic
import pytest

from rh_wizard.models.risk import RiskCeiling, RiskPolicy
from rh_wizard.risk.policy import apply_ceiling, build_effective_policy, effective_policy


def test_no_overrides_returns_defaults():
    defaults = RiskPolicy()
    assert effective_policy(defaults, None) == defaults
    assert effective_policy(defaults, {}) == defaults


def test_override_replaces_only_named_fields():
    defaults = RiskPolicy()
    eff = effective_policy(defaults, {"max_position_pct": "10", "max_trades_per_cycle": 2})
    assert eff.max_position_pct == Decimal("10")
    assert eff.max_trades_per_cycle == 2
    # untouched fields keep defaults
    assert eff.cash_reserve_pct == Decimal("10")


def test_unknown_override_key_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        effective_policy(RiskPolicy(), {"nonsense": 1})


def test_ceiling_none_returns_policy_unchanged():
    p = RiskPolicy(max_position_pct="80")
    assert apply_ceiling(p, None) == p


def test_ceiling_clamps_max_dials_down():
    p = RiskPolicy(
        max_position_pct="80",
        max_trades_per_cycle=50,
        slippage_band_pct="5",
        max_deploy_pct_per_cycle="90",
    )
    c = RiskCeiling(
        max_position_pct="25",
        max_trades_per_cycle=10,
        max_slippage_band_pct="1",
        max_deploy_pct_per_cycle="30",
    )
    clamped = apply_ceiling(p, c)
    assert clamped.max_position_pct == Decimal("25")
    assert clamped.max_trades_per_cycle == 10
    assert clamped.slippage_band_pct == Decimal("1")
    assert clamped.max_deploy_pct_per_cycle == Decimal("30")


def test_ceiling_clamps_min_dials_up():
    p = RiskPolicy(cash_reserve_pct="0", min_price="1", min_market_cap="0", min_avg_volume="0")
    c = RiskCeiling(
        min_cash_reserve_pct="10",
        min_price_floor="5",
        min_market_cap_floor="1000000000",
        min_avg_volume_floor="1000000",
    )
    clamped = apply_ceiling(p, c)
    assert clamped.cash_reserve_pct == Decimal("10")
    assert clamped.min_price == Decimal("5")
    assert clamped.min_market_cap == Decimal("1000000000")
    assert clamped.min_avg_volume == Decimal("1000000")


def test_ceiling_clamps_drawdown_down():
    # A safer kill-switch trips SOONER (smaller %). Ceiling caps it at the max allowed.
    p = RiskPolicy(drawdown_kill_switch_pct="90")
    c = RiskCeiling(max_drawdown_kill_switch_pct="20")
    assert apply_ceiling(p, c).drawdown_kill_switch_pct == Decimal("20")


def test_ceiling_does_not_tighten_already_safe_values():
    p = RiskPolicy(max_position_pct="10")  # already below the ceiling
    c = RiskCeiling(max_position_pct="25")
    assert apply_ceiling(p, c).max_position_pct == Decimal("10")


def test_build_effective_policy_merges_then_clamps():
    defaults = RiskPolicy()
    ceiling = RiskCeiling(max_position_pct="25")
    eff = build_effective_policy(defaults, ceiling, {"max_position_pct": "90"})
    assert eff.max_position_pct == Decimal("25")  # override 90 clamped to ceiling 25
