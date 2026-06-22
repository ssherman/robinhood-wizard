"""`wizard auth login` and `wizard accounts` commands."""

from __future__ import annotations

import webbrowser

import typer

from rh_wizard.auth.callback import OAuthCallbackServer
from rh_wizard.auth.oauth import build_oauth_provider
from rh_wizard.auth.token_storage import DiskTokenStorage
from rh_wizard.broker.client import make_broker_client
from rh_wizard.config import paths
from rh_wizard.config.settings import Settings, load_settings
from rh_wizard.logging.redaction import redact

auth_app = typer.Typer(help="Authenticate with the Robinhood Agentic MCP server.")


def _build_broker(settings: Settings):
    """Build an authenticated BrokerClient (real path; patched in tests)."""
    storage = DiskTokenStorage(paths.tokens_path())
    callback = OAuthCallbackServer(settings.oauth_redirect_host, settings.oauth_redirect_port)
    provider = build_oauth_provider(
        settings,
        storage,
        callback.redirect_uri,
        open_browser=lambda url: webbrowser.open(url),
        callback_handler=lambda: callback.wait_for_code(timeout=300),
    )
    return make_broker_client(settings, provider)


@auth_app.command("login")
def login() -> None:
    """Run the one-time browser consent and cache the refresh token."""
    paths.ensure_home()
    settings = load_settings()
    broker = _build_broker(settings)
    with broker:
        accounts = broker.get_accounts()
    typer.echo(f"Authenticated. Found {len(accounts)} account(s).")


def run_accounts() -> None:
    settings = load_settings()
    broker = _build_broker(settings)
    with broker:
        accounts = broker.get_accounts()
    for acct in accounts:
        typer.echo(redact(str(acct)))
