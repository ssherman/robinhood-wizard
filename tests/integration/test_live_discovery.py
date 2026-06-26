"""Live, opt-in DryRun cycle that DISCOVERS its universe from `intent` (no hand-picked
tickers). Read-only — no orders.

Run explicitly (needs a cached Robinhood token AND OPENAI_API_KEY):
    RH_WIZARD_LIVE=1 uv run --env-file .env pytest tests/integration/test_live_discovery.py -v -s
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live discovery cycle",
)


def test_live_discovery_cycle(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.discovery.web_llm import WebUniverseDiscoverer
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.provider import build_llm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.llm import LlmPlanner
    from rh_wizard.research.llm import LlmResearcher

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    settings = load_settings()
    strategy = Strategy(
        id="live-disc",
        name="Live Discovery",
        intent="Large-cap AI names with reasonable valuations.",
        universe=[],  # no hand-picked tickers — discovery must supply them
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
        discover=True,
        web_research=False,
        max_candidates=8,
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    llm = build_llm(settings)
    discoverer = WebUniverseDiscoverer(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=LlmResearcher(llm),
            planner=LlmPlanner(llm),
            journal=journal,
            discoverer=discoverer,
        )
        result = run_cycle(strategy, deps)
        print("\n" + render_cycle_result(result))
        assert result.run.status in {"completed", "aborted"}  # never crashes
        if result.run.status == "completed":
            assert result.discovery is not None
            assert len(result.discovery.tickers) >= 1  # discovered at least one ticker
            # the cycle journaled exactly what discovery reported
            assert len(journal.discovered_universe(result.run.run_id)) == len(
                result.discovery.tickers
            )
