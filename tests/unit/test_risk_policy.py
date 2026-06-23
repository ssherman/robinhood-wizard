from decimal import Decimal

import pydantic
import pytest

from rh_wizard.models.risk import RiskPolicy
from rh_wizard.risk.policy import effective_policy


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
