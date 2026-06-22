"""Typed wrapper over the Strands MCPClient bound to the Robinhood MCP server.

This is the single module that knows about MCP. ``BrokerClient`` adds typed helpers and
result parsing; ``make_broker_client`` builds the authenticated transport.
"""

from __future__ import annotations

import json
import uuid
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
        # Strands requires a unique tool_use_id per call.
        raw = self._mcp.call_tool_sync(
            tool_use_id=f"rhw-{uuid.uuid4().hex}",
            name=name,
            arguments=arguments or None,
        )
        return _coerce_payload(raw)

    def get_accounts(self) -> list[dict]:
        payload = self._call("get_accounts")
        return payload.get("data", {}).get("accounts", [])


def _coerce_payload(raw: Any) -> dict:
    """Normalize a Strands tool result into the MCP tool's JSON payload dict.

    Strands ``call_tool_sync`` returns an ``MCPToolResult`` (a dict): ``content`` is a list of
    ``{"text": ...}`` / ``{"json": ...}`` items, and ``structuredContent`` holds the raw
    structured dict when the tool provides it. Robinhood tools return their payload as a JSON
    string in a text item (and usually also as ``structuredContent``). Prefer the structured
    dict, then a json item, then a parsed text item.
    """
    if isinstance(raw, dict):
        structured = raw.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = raw.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("json"), dict):
                    return item["json"]
            for item in content:
                text = item.get("text") if isinstance(item, dict) else None
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        continue
            return {}
        # Legacy/simple dict payload (e.g. a {"data": {...}} fixture).
        return raw
    # Object whose .content is a JSON string (older shape).
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
