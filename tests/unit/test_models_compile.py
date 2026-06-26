from decimal import Decimal

from rh_wizard.models.compile import CompiledStrategy, CompileResult, SuggestedTicker
from rh_wizard.models.research import Source
from rh_wizard.models.signals import Signal
from rh_wizard.models.strategy import Strategy


def test_compiled_strategy_has_no_risk_field():
    assert "risk_overrides" not in CompiledStrategy.model_fields
    assert "risk" not in CompiledStrategy.model_fields


def test_compiled_strategy_parses_tickers_and_signals():
    c = CompiledStrategy(
        name="AI",
        intent="ai names",
        tickers=[SuggestedTicker(symbol="MSFT", rationale="azure")],
        signals_needed=[Signal.PE_RATIO, Signal.PRICE],
        cadence="weekly",
    )
    assert c.tickers[0].symbol == "MSFT"
    assert c.tickers[0].rationale == "azure"
    assert set(c.signals_needed) == {Signal.PE_RATIO, Signal.PRICE}
    assert c.cadence == "weekly"


def test_compile_result_carries_strategy_tickers_sources():
    r = CompileResult(
        strategy=Strategy(id="x", name="X"),
        tickers=[SuggestedTicker(symbol="MSFT")],
        sources=[Source(title="t", url="https://e/x")],
    )
    assert r.strategy.id == "x"
    assert r.tickers[0].symbol == "MSFT"
    assert r.sources[0].url == "https://e/x"


def test_compiled_bucket_fields():
    from rh_wizard.models.compile import CompiledBucket

    b = CompiledBucket(
        name="AI",
        target_pct="40",
        intent="ai leaders",
        tickers=[SuggestedTicker(symbol="NVDA", rationale="leader")],
    )
    assert b.name == "AI"
    assert b.target_pct == Decimal("40")
    assert b.intent == "ai leaders"
    assert b.tickers[0].symbol == "NVDA"


def test_compiled_strategy_holds_buckets():
    from rh_wizard.models.compile import CompiledBucket

    c = CompiledStrategy(
        name="Thematic",
        intent="themes",
        buckets=[CompiledBucket(name="AI", target_pct="40")],
    )
    assert c.tickers == []  # flat list empty in bucketed output
    assert c.buckets[0].name == "AI"


def test_compile_result_carries_buckets():
    from rh_wizard.models.compile import CompiledBucket

    r = CompileResult(
        strategy=Strategy(id="x", name="X"),
        tickers=[],
        sources=[Source(title="t", url="https://e/x")],
        buckets=[CompiledBucket(name="AI", target_pct="40")],
    )
    assert r.buckets[0].name == "AI"
    assert r.buckets[0].target_pct == Decimal("40")
