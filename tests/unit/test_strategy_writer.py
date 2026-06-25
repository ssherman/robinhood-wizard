from rh_wizard.models.compile import CompileResult, SuggestedTicker
from rh_wizard.models.research import Source
from rh_wizard.models.signals import Signal
from rh_wizard.models.strategy import Strategy
from rh_wizard.strategies.registry import StrategyRegistry
from rh_wizard.strategies.writer import write_strategy_yaml


def _result():
    strategy = Strategy(
        id="ai",
        name="AI",
        intent="ai names",
        universe=["MSFT", "META"],
        signals_needed={Signal.PRICE, Signal.PE_RATIO},
        cadence="weekly",
        risk_overrides={},
        web_research=True,
    )
    return CompileResult(
        strategy=strategy,
        tickers=[
            SuggestedTicker(symbol="MSFT", rationale="azure"),
            SuggestedTicker(symbol="META"),
        ],
        sources=[Source(title="Morningstar", url="https://e/ai")],
    )


def test_written_yaml_round_trips_to_equal_strategy(tmp_path):
    result = _result()
    write_strategy_yaml(tmp_path / "ai.yaml", result, "ai names with reasonable valuations")
    loaded = StrategyRegistry(tmp_path).load("ai")
    assert loaded == result.strategy


def test_written_yaml_has_review_header(tmp_path):
    result = _result()
    path = tmp_path / "ai.yaml"
    write_strategy_yaml(path, result, "ai names with reasonable valuations")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "Original thesis:" in text
    assert "ai names with reasonable valuations" in text
    assert "azure" in text  # per-ticker rationale
    assert "https://e/ai" in text  # source url


def test_written_yaml_round_trips_with_empty_tickers_and_sources(tmp_path):
    strategy = Strategy(
        id="empty",
        name="Empty",
        intent="nothing yet",
        universe=[],
        signals_needed=set(),
        risk_overrides={},
        web_research=True,
    )
    result = CompileResult(strategy=strategy, tickers=[], sources=[])
    path = tmp_path / "empty.yaml"
    write_strategy_yaml(path, result, "a thesis with no tickers")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#")
    loaded = StrategyRegistry(tmp_path).load("empty")
    assert loaded == result.strategy
