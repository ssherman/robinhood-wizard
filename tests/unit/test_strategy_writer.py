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


def _bucketed_result():
    from decimal import Decimal

    from rh_wizard.models.bucket import Bucket
    from rh_wizard.models.compile import CompiledBucket

    strategy = Strategy(
        id="thematic",
        name="Thematic",
        intent="10/70/20",
        signals_needed={Signal.PRICE, Signal.FRACTIONABLE},
        buckets=[
            Bucket(
                id="rare-earth",
                name="Rare Earth",
                target_pct=Decimal("10"),
                intent="rare earth",
                universe=["MP"],
            ),
            Bucket(id="value", name="Value", target_pct=Decimal("70"), universe=["BAC", "F"]),
        ],
        risk_overrides={},
    )
    return CompileResult(
        strategy=strategy,
        tickers=[],
        sources=[Source(title="Morningstar", url="https://e/v")],
        buckets=[
            CompiledBucket(
                name="Rare Earth",
                target_pct=Decimal("10"),
                tickers=[SuggestedTicker(symbol="MP", rationale="pure-play")],
            ),
            CompiledBucket(
                name="Value",
                target_pct=Decimal("70"),
                tickers=[SuggestedTicker(symbol="BAC", rationale="cheap bank")],
            ),
        ],
    )


def test_bucketed_yaml_round_trips_to_equal_strategy(tmp_path):
    result = _bucketed_result()
    write_strategy_yaml(tmp_path / "thematic.yaml", result, "10% rare earth, 70% value")
    loaded = StrategyRegistry(tmp_path).load("thematic")
    assert loaded == result.strategy


def test_bucketed_yaml_header_groups_tickers_per_bucket(tmp_path):
    result = _bucketed_result()
    path = tmp_path / "thematic.yaml"
    write_strategy_yaml(path, result, "10% rare earth, 70% value")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "Rare Earth" in text and "Value" in text  # bucket names in the header
    assert "pure-play" in text  # per-ticker rationale
    assert "https://e/v" in text  # source url
    # the active YAML carries buckets, not a top-level universe
    assert "buckets:" in text
    assert "\nuniverse:" not in text


def test_bucketed_yaml_round_trips_non_integral_decimals(tmp_path):
    from decimal import Decimal

    from rh_wizard.models.bucket import Bucket

    strategy = Strategy(
        id="frac",
        name="Frac",
        signals_needed={Signal.PRICE, Signal.FRACTIONABLE},
        rebalance_band_pct=Decimal("2.5"),
        buckets=[Bucket(id="a", name="A", target_pct=Decimal("12.5"), universe=["NVDA"])],
        risk_overrides={},
    )
    result = CompileResult(strategy=strategy, tickers=[], sources=[], buckets=[])
    write_strategy_yaml(tmp_path / "frac.yaml", result, "fractional targets")
    loaded = StrategyRegistry(tmp_path).load("frac")
    assert loaded == result.strategy
    assert loaded.buckets[0].target_pct == Decimal("12.5")  # exact, no float drift
    assert loaded.rebalance_band_pct == Decimal("2.5")
