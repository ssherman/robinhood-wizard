"""Live, opt-in DryRun cycle smoke against the real Robinhood MCP (read-only — no orders).

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_run.py -v -s

Runs the full deterministic cycle (reconcile -> resolve -> stub research/plan -> risk vet ->
journal) and prints the rendered DryRun result. Places NO orders.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live DryRun cycle smoke",
)


def test_live_dryrun_cycle(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.stub import StubPlanner
    from rh_wizard.research.stub import StubResearcher

    settings = load_settings()
    strategy = Strategy(
        id="live-smoke",
        name="Live Smoke",
        universe=["AAPL", "MSFT"],
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=StubResearcher(),
            planner=StubPlanner(),
            journal=journal,
        )
        result = run_cycle(strategy, deps)
        rendered = render_cycle_result(result)
        recorded = journal.recent_runs()

    print("\n" + rendered)
    assert result.run.status == "completed"
    assert result.vetted is not None
    assert recorded and recorded[0].run_id == result.run.run_id
