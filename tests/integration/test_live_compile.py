"""Live, opt-in compile against the REAL OpenAI web-search API (no broker, no orders).

Run explicitly (needs OPENAI_API_KEY):
    RH_WIZARD_LIVE=1 uv run --env-file .env pytest tests/integration/test_live_compile.py -v -s
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live web-search compile",
)


def test_live_compile_suggests_universe(tmp_path):
    from rh_wizard.config.settings import load_settings
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm
    from rh_wizard.strategies.compiler import LlmStrategyCompiler
    from rh_wizard.strategies.writer import write_strategy_yaml

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    settings = load_settings()
    compiler = LlmStrategyCompiler(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))
    prose = "Large-cap AI names with reasonable valuations; favor a few high-conviction picks."
    result = compiler.compile("live-ai", prose)

    path = tmp_path / "live-ai.yaml"
    write_strategy_yaml(path, result, prose)
    print("\n" + path.read_text(encoding="utf-8"))

    assert result.strategy.id == "live-ai"
    assert result.strategy.risk_overrides == {}
    assert len(result.strategy.universe) >= 1  # the model suggested at least one ticker
    assert len(result.sources) >= 1  # web_search produced citations
