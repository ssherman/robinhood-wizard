"""Typed wrapper over the Strands MCPClient bound to the Robinhood MCP server.

This is the single module that knows about MCP. ``BrokerClient`` adds typed helpers and
result parsing; ``make_broker_client`` builds the authenticated transport. The transport
construction is verified against the installed ``mcp`` version in Task 9 (see the §18 note
in the task header).
"""

from __future__ import annotations

import json
from typing import Any

from rh_wizard.config.settings import Settings


class BrokerClient:
    def __init__(self, mcp_client: Any) -> None:
        self._mcp = mcp_client

    def __enter__(self) -> BrokerClient:
        self._mcp.__enter__()
        return self

    def __exit__(self, *exc) -> bool:
        return bool(self._mcp.__exit__(*exc))

    def list_tool_names(self) -> list[str]:
        return [t.tool_name for t in self._mcp.list_tools_sync()]

    def _call(self, name: str, **arguments: Any) -> dict:
        raw = self._mcp.call_tool_sync(name=name, arguments=arguments or None)
        return _coerce_payload(raw)

    def get_accounts(self) -> list[dict]:
        payload = self._call("get_accounts")
        return payload.get("data", {}).get("results", [])


def _coerce_payload(raw: Any) -> dict:
    """Normalize an MCP tool result into a dict.

    Strands may return the structured content directly, or a result object whose text
    content holds a JSON string. Handle both.
    """
    if isinstance(raw, dict):
        return raw
    text = getattr(raw, "content", None)
    if isinstance(text, str):
        return json.loads(text)
    return {}


def make_broker_client(settings: Settings, oauth_provider: Any) -> BrokerClient:
    import httpx
    from mcp.client.streamable_http import streamable_http_client
    from strands.tools.mcp import MCPClient

    def transport():
        http = httpx.AsyncClient(auth=oauth_provider, follow_redirects=True)
        return streamable_http_client(settings.robinhood_mcp_url, http_client=http)

    return BrokerClient(MCPClient(transport))
