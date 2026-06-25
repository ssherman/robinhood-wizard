"""Live, opt-in DryRun cycle with the REAL LLM research/plan agents (read-only — no orders).

Run explicitly (needs a cached Robinhood token AND OPENAI_API_KEY):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_research.py -v -s
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live LLM research cycle",
)


def test_live_llm_dryrun_cycle(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.llm.provider import build_llm
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.llm import LlmPlanner
    from rh_wizard.research.llm import LlmResearcher

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    settings = load_settings()
    strategy = Strategy(
        id="live-llm",
        name="Live LLM",
        intent="Prefer large-cap technology names with reasonable valuations.",
        universe=["AAPL", "MSFT", "NVDA"],
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    llm = build_llm(settings)
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=LlmResearcher(llm),
            planner=LlmPlanner(llm),
            journal=journal,
        )
        result = run_cycle(strategy, deps)
        print("\n" + render_cycle_result(result))

    assert result.run.status in {"completed", "aborted"}  # never crashes
    if result.run.status == "completed":
        assert result.report is not None
        assert result.vetted is not None


def test_live_web_research_cycle(tmp_path):
    import os

    import pytest

    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.provider import build_llm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.llm import LlmPlanner
    from rh_wizard.research.web_llm import WebLlmResearcher

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    settings = load_settings()
    strategy = Strategy(
        id="live-web",
        name="Live Web",
        intent="Prefer large-cap technology names with reasonable valuations.",
        universe=["AAPL", "MSFT", "NVDA"],
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
        web_research=True,
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    researcher = WebLlmResearcher(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=researcher,
            planner=LlmPlanner(build_llm(settings)),
            journal=journal,
        )
        result = run_cycle(strategy, deps)
        print("\n" + render_cycle_result(result))
        assert result.run.status in {"completed", "aborted"}  # never crashes
        if result.run.status == "completed":
            assert result.report is not None
            # the cycle must journal exactly the sources the researcher reported
            assert len(journal.research_sources(result.run.run_id)) == len(result.report.sources)
