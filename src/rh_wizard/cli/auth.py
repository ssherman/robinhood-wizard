"""`wizard auth login` and `wizard accounts` commands."""

from __future__ import annotations

import asyncio
import webbrowser
from urllib.parse import parse_qs, urlsplit

import typer

from rh_wizard.auth.oauth import build_oauth_provider
from rh_wizard.auth.token_storage import DiskTokenStorage
from rh_wizard.broker.client import make_broker_client
from rh_wizard.config import paths
from rh_wizard.config.settings import Settings, load_settings
from rh_wizard.logging.redaction import redact
from rh_wizard.masking import mask_account

auth_app = typer.Typer(help="Authenticate with the Robinhood Agentic MCP server.")


def _redirect_uri(settings: Settings) -> str:
    return f"http://{settings.oauth_redirect_host}:{settings.oauth_redirect_port}/callback"


async def _redirect_handler(url: str) -> None:
    """Open the Robinhood consent page, and always print the URL as a fallback.

    Async because the mcp SDK awaits this handler.
    """
    typer.echo("\nAuthorize Robinhood Wizard in your browser (opening it now):\n")
    typer.echo(f"  {url}\n")
    try:
        webbrowser.open(url)
    except Exception:  # browser launch is best-effort; the printed URL is the fallback
        pass


async def _paste_callback_handler() -> tuple[str, str | None]:
    """Read the OAuth redirect URL the user pastes and extract (code, state).

    This avoids any dependence on localhost being reachable from the browser (the page at
    the redirect URL may fail to load, e.g. under WSL — that's fine, the code is in the
    address bar). Async because the mcp SDK awaits this handler.
    """
    typer.echo(
        "After approving, copy the FULL URL your browser was redirected to\n"
        "(it looks like http://localhost:3030/callback?code=...&state=...) and paste it below.\n"
        "The page itself may fail to load — that's expected; just copy its address."
    )
    pasted = (await asyncio.to_thread(input, "Redirect URL: ")).strip()
    query = parse_qs(urlsplit(pasted).query)
    code = (query.get("code") or [None])[0]
    state = (query.get("state") or [None])[0]
    if not code:
        raise ValueError("No ?code= found in the pasted URL — paste the full redirect URL.")
    return code, state


def _build_broker(settings: Settings):
    """Build an authenticated BrokerClient (real path; patched in tests)."""
    storage = DiskTokenStorage(paths.tokens_path())
    provider = build_oauth_provider(
        settings,
        storage,
        _redirect_uri(settings),
        _redirect_handler,
        _paste_callback_handler,
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
        shown = dict(acct)
        if "account_number" in shown:
            shown["account_number"] = mask_account(str(shown["account_number"]))
        typer.echo(redact(str(shown)))
