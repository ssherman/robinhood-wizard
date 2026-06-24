"""`wizard data SYMBOLS...` — resolve and show market data for a few symbols.

A thin, read-only inspection command (and the live-verification path for the data layer),
paralleling `wizard positions`. Resolves every signal the Robinhood source provides.
"""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_market_context
from rh_wizard.config.settings import load_settings
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.data.robinhood import RobinhoodDataSource


def run_data(symbols: list[str]) -> None:
    settings = load_settings()
    broker = auth._build_broker(settings)
    source = RobinhoodDataSource(broker)
    universe = [s.upper() for s in symbols]
    with broker:
        context = SignalResolver([source]).resolve(universe, source.provides())
    typer.echo(render_market_context(context))
