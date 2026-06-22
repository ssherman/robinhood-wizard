"""Assemble the mcp SDK OAuthClientProvider for the Robinhood Agentic MCP server.

The pure ``build_client_metadata`` / ``oauth_base_url`` helpers are unit-tested. The
``build_oauth_provider`` assembler imports the SDK lazily and is exercised live in
Task 9 (it needs a browser + real server).
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from rh_wizard.config.settings import Settings


def oauth_base_url(settings: Settings) -> str:
    parts = urlsplit(settings.robinhood_mcp_url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def build_client_metadata(settings: Settings, redirect_uri: str) -> dict:
    return {
        "client_name": settings.oauth_client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def build_oauth_provider(
    settings: Settings,
    storage,
    redirect_uri: str,
    open_browser: Callable[[str], None],
    callback_handler,
):
    """Construct an OAuthClientProvider. SDK imported lazily; verify signature in Task 9."""
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    return OAuthClientProvider(
        server_url=oauth_base_url(settings),
        client_metadata=OAuthClientMetadata.model_validate(
            build_client_metadata(settings, redirect_uri)
        ),
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=callback_handler,
    )
