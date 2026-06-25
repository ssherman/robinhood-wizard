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
