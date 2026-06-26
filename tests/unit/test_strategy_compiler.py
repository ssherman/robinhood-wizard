import pytest

from rh_wizard.models.compile import CompiledStrategy, SuggestedTicker
from rh_wizard.models.research import Source
from rh_wizard.models.signals import Signal
from rh_wizard.strategies.compiler import (
    COMPILE_SYSTEM,
    LlmStrategyCompiler,
    StrategyCompiler,
)


class FakeWebSearchLlm:
    def __init__(self):
        self.last_model = None
        self.last_prompt = None
        self.last_system = None

    def research(self, output_model, prompt, system=""):
        self.last_model = output_model
        self.last_prompt = prompt
        self.last_system = system
        compiled = output_model(
            name="Large-Cap AI",
            intent="large-cap ai names with reasonable valuations",
            tickers=[
                SuggestedTicker(symbol="MSFT", rationale="azure ai at a fair multiple"),
                SuggestedTicker(symbol="META", rationale="cheap mega-cap ai"),
            ],
            signals_needed=[Signal.PE_RATIO, Signal.PRICE],
            cadence="weekly",
        )
        return compiled, [Source(title="src", url="https://e/ai")]


def test_compile_maps_compiled_strategy_into_strategy():
    fake = FakeWebSearchLlm()
    result = LlmStrategyCompiler(fake).compile(
        "ai-large-cap", "large-cap ai with reasonable valuations"
    )
    s = result.strategy
    assert s.id == "ai-large-cap"
    assert s.name == "Large-Cap AI"
    assert s.intent == "large-cap ai names with reasonable valuations"
    assert s.universe == ["MSFT", "META"]
    assert s.signals_needed == {Signal.PE_RATIO, Signal.PRICE}
    assert s.cadence == "weekly"
    assert s.web_research is True
    assert s.risk_overrides == {}
    assert [t.symbol for t in result.tickers] == ["MSFT", "META"]
    assert [src.url for src in result.sources] == ["https://e/ai"]
    assert fake.last_model is CompiledStrategy
    assert fake.last_system == COMPILE_SYSTEM
    assert "large-cap ai with reasonable valuations" in fake.last_prompt


def test_compile_always_empties_risk_overrides():
    # CompiledStrategy has no risk field; risk_overrides is always {}.
    result = LlmStrategyCompiler(FakeWebSearchLlm()).compile("x", "anything")
    assert result.strategy.risk_overrides == {}


def test_satisfies_compiler_protocol():
    assert isinstance(LlmStrategyCompiler(FakeWebSearchLlm()), StrategyCompiler)


class FakeBucketedLlm:
    def research(self, output_model, prompt, system=""):
        from rh_wizard.models.compile import CompiledBucket

        compiled = output_model(
            name="Thematic",
            intent="10% rare earth, 70% large-cap value, 20% cannabis",
            buckets=[
                CompiledBucket(
                    name="Rare Earth",
                    target_pct="10",
                    intent="small-cap rare earth",
                    tickers=[SuggestedTicker(symbol="MP", rationale="pure-play")],
                ),
                CompiledBucket(
                    name="Large-Cap Value",
                    target_pct="70",
                    intent="large-cap value under $100",
                    tickers=[SuggestedTicker(symbol="BAC"), SuggestedTicker(symbol="F")],
                ),
                CompiledBucket(
                    name="Cannabis",
                    target_pct="20",
                    tickers=[SuggestedTicker(symbol="MSOS")],
                ),
            ],
            signals_needed=[Signal.PRICE, Signal.MARKET_CAP],
        )
        return compiled, [Source(title="src", url="https://e/x")]


def test_compile_assembles_bucketed_strategy():
    from decimal import Decimal

    result = LlmStrategyCompiler(FakeBucketedLlm()).compile("thematic", "10/70/20 prose")
    s = result.strategy
    assert [b.id for b in s.buckets] == ["rare-earth", "large-cap-value", "cannabis"]
    assert [b.target_pct for b in s.buckets] == [Decimal("10"), Decimal("70"), Decimal("20")]
    assert s.buckets[1].universe == ["BAC", "F"]  # suggestions frozen as the bucket universe
    assert all(b.discover is False for b in s.buckets)
    assert s.universe == []  # bucketed: no top-level universe (mutually exclusive)
    assert Signal.FRACTIONABLE in s.signals_needed  # allocator needs it
    assert s.risk_overrides == {}
    assert result.tickers == []  # flat list empty for bucketed
    assert [b.name for b in result.buckets] == ["Rare Earth", "Large-Cap Value", "Cannabis"]


def test_compile_slug_dedupes_collisions():
    from rh_wizard.models.compile import CompiledBucket

    class DupLlm:
        def research(self, output_model, prompt, system=""):
            compiled = output_model(
                name="Dup",
                buckets=[
                    CompiledBucket(name="AI", target_pct="50"),
                    CompiledBucket(name="A I", target_pct="50"),  # slugs to "a-i" vs "ai"
                ],
            )
            return compiled, []

    s = LlmStrategyCompiler(DupLlm()).compile("dup", "x").strategy
    ids = [b.id for b in s.buckets]
    assert len(set(ids)) == len(ids)  # all unique


def test_compile_over_allocation_raises():
    import pydantic

    from rh_wizard.models.compile import CompiledBucket

    class OverLlm:
        def research(self, output_model, prompt, system=""):
            compiled = output_model(
                name="Over",
                buckets=[
                    CompiledBucket(name="A", target_pct="60"),
                    CompiledBucket(name="B", target_pct="60"),
                ],
            )
            return compiled, []

    with pytest.raises(pydantic.ValidationError):
        LlmStrategyCompiler(OverLlm()).compile("over", "x")
