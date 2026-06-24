import pytest

from rh_wizard.models.signals import Signal
from rh_wizard.strategies.registry import StrategyNotFoundError, StrategyRegistry


def _write(dirpath, name, text):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(text)


def test_list_returns_sorted_stems(tmp_path):
    d = tmp_path / "strategies"
    _write(d, "b.yaml", "id: b\nname: B\n")
    _write(d, "a.yaml", "id: a\nname: A\n")
    assert StrategyRegistry(d).list() == ["a", "b"]


def test_list_empty_when_dir_missing(tmp_path):
    assert StrategyRegistry(tmp_path / "nope").list() == []


def test_load_parses_strategy(tmp_path):
    d = tmp_path / "strategies"
    _write(
        d,
        "momentum.yaml",
        "id: momentum\nname: Momentum\nintent: buy strong names\n"
        "universe: [AAPL, MSFT]\nsignals_needed: [price, market_cap]\n"
        "risk_overrides:\n  max_position_pct: 15\n",
    )
    s = StrategyRegistry(d).load("momentum")
    assert s.name == "Momentum"
    assert s.universe == ["AAPL", "MSFT"]
    assert s.signals_needed == {Signal.PRICE, Signal.MARKET_CAP}
    assert s.risk_overrides == {"max_position_pct": 15}


def test_load_missing_raises(tmp_path):
    with pytest.raises(StrategyNotFoundError):
        StrategyRegistry(tmp_path / "strategies").load("ghost")
