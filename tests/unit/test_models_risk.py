from decimal import Decimal

from rh_wizard.models.risk import RiskCeiling, RiskPolicy


def test_riskpolicy_conservative_defaults():
    p = RiskPolicy()
    assert p.max_position_pct == Decimal("20")
    assert p.cash_reserve_pct == Decimal("10")
    assert p.max_trades_per_cycle == 5
    assert p.max_deploy_pct_per_cycle == Decimal("30")
    assert p.slippage_band_pct == Decimal("0.5")
    assert p.min_price == Decimal("5")
    assert p.min_avg_volume == Decimal("1000000")
    assert p.min_market_cap == Decimal("1000000000")
    assert p.drawdown_kill_switch_pct == Decimal("15")


def test_riskpolicy_coerces_and_forbids_extra():
    import pydantic
    import pytest

    p = RiskPolicy(max_position_pct="25")
    assert p.max_position_pct == Decimal("25")
    with pytest.raises(pydantic.ValidationError):
        RiskPolicy(unknown_field=1)


def test_riskceiling_fields_default_none():
    c = RiskCeiling()
    assert c.max_position_pct is None
    assert c.min_cash_reserve_pct is None
    assert c.max_drawdown_kill_switch_pct is None
