"""Root Typer application for the `wizard` CLI."""

from __future__ import annotations

import logging

import typer

from rh_wizard.cli.auth import auth_app, run_accounts
from rh_wizard.logging.mcp_noise import silence_session_termination_warning
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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    install_redaction(logging.getLogger())
    silence_session_termination_warning()
    app()


if __name__ == "__main__":
    main()
