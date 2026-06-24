"""`wizard run <strategy>` (DryRun cycle) and `wizard strategies` (list)."""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_cycle_result
from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.core.cycle import CycleDeps, run_cycle
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.data.robinhood import RobinhoodDataSource
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.cycle import CycleMode
from rh_wizard.planning.stub import StubPlanner
from rh_wizard.research.stub import StubResearcher
from rh_wizard.strategies.registry import StrategyNotFoundError, StrategyRegistry


def list_strategies() -> None:
    registry = StrategyRegistry(paths.strategies_dir())
    ids = registry.list()
    if not ids:
        typer.echo(f"No strategies found in {paths.strategies_dir()}.")
        return
    for sid in ids:
        typer.echo(sid)


def run_strategy(strategy_id: str) -> None:
    paths.ensure_home()
    settings = load_settings()
    registry = StrategyRegistry(paths.strategies_dir())
    try:
        strategy = registry.load(strategy_id)
    except StrategyNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    with broker, SqliteJournal(paths.db_path()) as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=StubResearcher(),
            planner=StubPlanner(),
            journal=journal,
        )
        result = run_cycle(strategy, deps, CycleMode.DRY_RUN)
    typer.echo(render_cycle_result(result))
