"""Assemble the mcp SDK OAuthClientProvider for the Robinhood Agentic MCP server.

The pure ``build_client_metadata`` helper is unit-tested. The ``build_oauth_provider``
assembler imports the SDK lazily and is exercised live (it needs a browser + real server).
"""

from __future__ import annotations

from collections.abc import Callable

from rh_wizard.config.settings import Settings


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
    """Construct an OAuthClientProvider. SDK imported lazily.

    server_url must be the FULL MCP URL (including the ``/mcp/trading`` path): Robinhood's
    protected-resource metadata advertises that exact resource, and the SDK validates the
    configured resource against it. Passing the base host fails with OAuthFlowError
    ("Protected resource ... does not match expected ...").
    """
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    return OAuthClientProvider(
        server_url=settings.robinhood_mcp_url,
        client_metadata=OAuthClientMetadata.model_validate(
            build_client_metadata(settings, redirect_uri)
        ),
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=callback_handler,
    )
