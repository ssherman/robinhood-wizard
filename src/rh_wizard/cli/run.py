"""`wizard run <strategy>` (DryRun cycle) and `wizard strategies` (list)."""

from __future__ import annotations

from decimal import Decimal

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_cycle_result
from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.core.cycle import CycleDeps, run_cycle
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.data.robinhood import RobinhoodDataSource
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.portfolio import PortfolioOverride, resolve_account_number
from rh_wizard.models.cycle import CycleMode
from rh_wizard.planning.llm import LlmPlanner
from rh_wizard.research.llm import LlmResearcher
from rh_wizard.strategies.registry import StrategyNotFoundError, StrategyRegistry


def _build_llm(settings):
    """Build the research/plan LLM (real path; patched in tests)."""
    from rh_wizard.llm.provider import build_llm

    return build_llm(settings)


def _build_web_researcher(settings):
    """Build the web-search researcher (real path; patched in tests)."""
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm
    from rh_wizard.research.web_llm import WebLlmResearcher

    return WebLlmResearcher(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))


def _build_discoverer(settings):
    """Build the web-search-backed universe discoverer (real path; patched in tests)."""
    from rh_wizard.discovery.web_llm import WebUniverseDiscoverer
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm

    return WebUniverseDiscoverer(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))


def _build_recommender(settings):
    """Build the web-search-backed bucket recommender (real path; patched in tests)."""
    from rh_wizard.allocation.web_llm import WebBucketRecommender
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm

    return WebBucketRecommender(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))


def _build_executor(broker):
    """Build the real order executor (patched in tests)."""
    from rh_wizard.execution.robinhood import RobinhoodOrderExecutor

    return RobinhoodOrderExecutor(broker)


def _build_approval():
    """Build the interactive approval gate (patched in tests)."""
    from rh_wizard.cli.approval import CliApprovalGate

    return CliApprovalGate()


def list_strategies() -> None:
    registry = StrategyRegistry(paths.strategies_dir())
    ids = registry.list()
    if not ids:
        typer.echo(f"No strategies found in {paths.strategies_dir()}.")
        return
    for sid in ids:
        typer.echo(sid)


def run_strategy(
    strategy_id: str,
    execute: bool = False,
    capital: Decimal | None = None,
    ignore_holdings: bool = False,
) -> None:
    paths.ensure_home()
    settings = load_settings()
    registry = StrategyRegistry(paths.strategies_dir())
    try:
        strategy = registry.load(strategy_id)
    except StrategyNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    override = PortfolioOverride(capital=capital, ignore_holdings=ignore_holdings)
    if execute and override.active:
        raise typer.BadParameter(
            "--execute cannot be combined with --capital/--ignore-holdings; "
            "research/what-if runs never place orders."
        )
    if capital is not None and capital <= 0:
        raise typer.BadParameter("--capital must be a positive dollar amount.")
    do_execute = execute and not override.active

    broker = auth._build_broker(settings)
    with broker, SqliteJournal(paths.db_path()) as journal:
        # Resolve the trading account up front so the data layer can call account-scoped tools
        # (get_equity_tradability, for the fractionable signal) correctly.
        account_number = resolve_account_number(broker, settings)
        resolver = SignalResolver([RobinhoodDataSource(broker, account_number)])
        llm = _build_llm(settings)
        researcher = (
            _build_web_researcher(settings) if strategy.web_research else LlmResearcher(llm)
        )
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=researcher,
            planner=LlmPlanner(llm),
            journal=journal,
            discoverer=(
                _build_discoverer(settings)
                if strategy.discover or any(b.discover for b in strategy.buckets)
                else None
            ),
            recommender=_build_recommender(settings) if strategy.buckets else None,
            executor=_build_executor(broker) if do_execute else None,
            approval=_build_approval() if do_execute else None,
        )
        mode = CycleMode.HUMAN_APPROVAL if do_execute else CycleMode.DRY_RUN
        result = run_cycle(strategy, deps, mode, override=override if override.active else None)
    typer.echo(render_cycle_result(result))
