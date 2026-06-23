from rh_wizard.models.signals import RISK_SIGNALS, Signal


def test_signal_values_are_lowercase_names():
    assert Signal.PRICE.value == "price"
    assert Signal.MARKET_CAP.value == "market_cap"
    assert Signal.WEEK_52_HIGH.value == "week_52_high"


def test_signal_is_str_enum():
    # str-Enum members compare equal to their string value (YAML/JSON friendly).
    assert Signal.SECTOR == "sector"


def test_declared_seam_signals_exist():
    # Defined but not provided in Phase 3 (NEWS/SENTIMENT come from the Phase 4 agent).
    for name in ("HISTORICALS", "EARNINGS", "NEWS", "SENTIMENT"):
        assert hasattr(Signal, name)


def test_risk_signals_are_the_symbolrisk_inputs():
    assert RISK_SIGNALS == frozenset({Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP})
