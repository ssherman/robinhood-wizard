"""Root Typer application for the `wizard` CLI."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

import typer

from rh_wizard.cli.auth import auth_app, run_accounts
from rh_wizard.cli.compile import compile_strategy
from rh_wizard.cli.market import run_data
from rh_wizard.cli.portfolio import run_history, run_positions
from rh_wizard.cli.run import list_strategies, run_strategy
from rh_wizard.logging.mcp_noise import silence_session_termination_warning
from rh_wizard.logging.quiet import quiet_dependency_logs
from rh_wizard.logging.redaction import install_redaction

DISCLAIMER = (
    "DISCLAIMER: Not financial advice. No warranty. Use at your own risk. "
    "The authors are not liable for any financial loss."
)

app = typer.Typer(help=f"Robinhood Wizard.\n\n{DISCLAIMER}")
app.add_typer(auth_app, name="auth")


@app.command()
def accounts() -> None:
    """Connect to Robinhood and list your agentic account(s)."""
    run_accounts()


@app.command()
def positions() -> None:
    """Reconcile live broker state and show current holdings."""
    run_positions()


@app.command()
def history(
    limit: int = typer.Option(50, help="Max number of orders to show."),
    since: str | None = typer.Option(
        None, help="Only sync orders on/after this date (YYYY-MM-DD)."
    ),
) -> None:
    """Sync broker order history into the journal and show recent trades."""
    run_history(limit, since)


@app.command()
def data(
    symbols: list[str] = typer.Argument(..., help="Ticker symbols, e.g. AAPL MSFT."),  # noqa: B008
) -> None:
    """Resolve and show market data (quotes + fundamentals) for SYMBOLS."""
    run_data(symbols)


@app.command()
def strategies() -> None:
    """List strategies available in ~/.rh-wizard/strategies/."""
    list_strategies()


@app.command()
def run(
    strategy_id: str = typer.Argument(..., help="Strategy id (yaml filename stem)."),  # noqa: B008
    execute: bool = typer.Option(  # noqa: B008
        False,
        "--execute",
        help="Place REAL orders after a typed confirmation (HumanApproval). "
        "Default is DryRun (no orders).",
    ),
    capital: float | None = typer.Option(  # noqa: B008
        None,
        "--capital",
        help="Size to this dollar amount instead of your account's cash (research/what-if; "
        "no orders).",
    ),
    ignore_holdings: bool = typer.Option(  # noqa: B008
        False,
        "--ignore-holdings",
        help="Treat your account as having no positions — a clean slate (research/what-if; "
        "no orders).",
    ),
) -> None:
    """Run STRATEGY_ID. Default is DryRun — proposes a vetted plan and places NO orders.
    With --execute: places REAL orders after a typed confirmation (HumanApproval).
    With --capital/--ignore-holdings: a read-only research/what-if run (never places orders)."""
    cap = Decimal(str(capital)) if capital is not None else None
    run_strategy(strategy_id, execute=execute, capital=cap, ignore_holdings=ignore_holdings)


@app.command()
def compile(
    strategy_id: str = typer.Argument(..., help="Strategy id (yaml filename stem)."),  # noqa: B008
    file: Path | None = typer.Option(  # noqa: B008
        None, "--file", "-f", help="Read the strategy description from this file."
    ),
    text: str | None = typer.Option(  # noqa: B008
        None, "--text", "-t", help="The strategy description inline."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing strategy file."),  # noqa: B008
) -> None:
    """Compile a plain-language description into a reviewable strategy YAML (no orders)."""
    compile_strategy(strategy_id, file, text, force)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    quiet_dependency_logs()  # keep httpx/openai/mcp INFO spam from burying the --execute prompt
    install_redaction(logging.getLogger())
    silence_session_termination_warning()
    app()


if __name__ == "__main__":
    main()
