"""`wizard positions` and `wizard history` commands."""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_history, render_positions
from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile, resolve_account_number
from rh_wizard.memory.sync import sync_equity_orders


def run_positions() -> None:
    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        state = reconcile(broker, settings)
        state = enrich_with_quotes(state, broker)
    typer.echo(render_positions(state))


def run_history(limit: int = 50, since: str | None = None) -> None:
    paths.ensure_home()
    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        account_number = resolve_account_number(broker, settings)
        with SqliteJournal(paths.db_path()) as journal:
            sync_equity_orders(broker, account_number, journal, created_at_gte=since)
            trades = journal.recent_trades(limit)
    typer.echo(render_history(trades))
