import pydantic
import pytest

from rh_wizard.models.signals import Signal
from rh_wizard.models.strategy import Strategy


def test_strategy_minimal_defaults():
    s = Strategy(id="momentum", name="Momentum")
    assert s.id == "momentum"
    assert s.intent == ""
    assert s.universe == []
    assert s.signals_needed == set()
    assert s.cadence is None
    assert s.risk_overrides == {}


def test_strategy_coerces_signals_from_strings():
    s = Strategy(id="m", name="M", universe=["AAPL"], signals_needed=["price", "market_cap"])
    assert s.signals_needed == {Signal.PRICE, Signal.MARKET_CAP}


def test_strategy_holds_intent_and_overrides():
    s = Strategy(
        id="m", name="M", intent="20% energy, 40% AI", risk_overrides={"max_position_pct": "15"}
    )
    assert s.intent.startswith("20% energy")
    assert s.risk_overrides == {"max_position_pct": "15"}


def test_strategy_forbids_unknown_fields():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", bogus=1)
