"""`wizard positions` and `wizard history` commands."""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_positions
from rh_wizard.config.settings import load_settings
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile


def run_positions() -> None:
    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        state = reconcile(broker, settings)
        state = enrich_with_quotes(state, broker)
    typer.echo(render_positions(state))
