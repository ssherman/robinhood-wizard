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

    def get_portfolio(self, account_number: str) -> dict:
        return self._call("get_portfolio", account_number=account_number)

    def get_equity_positions(self, account_number: str) -> list[dict]:
        return self._paginate("get_equity_positions", "positions", account_number=account_number)

    def get_equity_quotes(self, symbols: list[str]) -> list[dict]:
        """Return the live ``quote`` object for each symbol (symbol + prices at top level).

        Live-confirmed (Phase 1 §18): the payload is ``data.results[]``, where each entry
        pairs ``{"quote": {...}, "close": {...}}``. We unwrap to the inner ``quote`` dict so
        callers see ``symbol`` / ``last_trade_price`` directly. A flat shape is tolerated.
        """
        if not symbols:
            return []
        payload = self._call("get_equity_quotes", symbols=list(symbols))
        items = _extract_list(payload, "results") or _extract_list(payload, "quotes")
        quotes: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            inner = item.get("quote")
            quotes.append(inner if isinstance(inner, dict) else item)
        return quotes

    def get_equity_fundamentals(self, symbols: list[str]) -> list[dict]:
        """Return one fundamentals dict per symbol (market cap, avg volume, P/E, P/B,
        sector/industry, 52-wk range, dividend).

        Payload shape unconfirmed until live verification (Phase 3, spec §18) — defensively
        unwrap ``data.results``/``data.fundamentals``, tolerating a flat list.
        """
        if not symbols:
            return []
        payload = self._call("get_equity_fundamentals", symbols=list(symbols))
        return _extract_list(payload, "results") or _extract_list(payload, "fundamentals")

    def get_equity_tradability(self, symbols: list[str]) -> list[dict]:
        """Return one tradability dict per symbol (whether fractional orders are supported).

        Payload shape unconfirmed until live verification (Phase 4e, spec §18) — defensively
        unwrap ``data.results``/``data.tradability``, tolerating a flat list.
        """
        if not symbols:
            return []
        payload = self._call("get_equity_tradability", symbols=list(symbols))
        return _extract_list(payload, "results") or _extract_list(payload, "tradability")

    def get_equity_orders(
        self,
        account_number: str,
        *,
        created_at_gte: str | None = None,
        state: str | None = None,
        placed_agent: str | None = None,
    ) -> list[dict]:
        args: dict[str, Any] = {"account_number": account_number}
        if created_at_gte:
            args["created_at_gte"] = created_at_gte
        if state:
            args["state"] = state
        if placed_agent:
            args["placed_agent"] = placed_agent
        return self._paginate("get_equity_orders", "orders", **args)

    def _paginate(self, name: str, key: str, **arguments: Any) -> list[dict]:
        """Follow ``next`` cursors, flattening the ``key`` list across all pages."""
        items: list[dict] = []
        cursor: str | None = None
        while True:
            args = {**arguments, "cursor": cursor} if cursor else dict(arguments)
            payload = self._call(name, **args)
            items.extend(_extract_list(payload, key))
            cursor = _next_cursor(payload)
            if not cursor:
                return items


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


def _extract_list(payload: dict, key: str) -> list[dict]:
    """Pull a results list out of a tool payload, tolerant of nesting shape."""
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    if isinstance(payload.get(key), list):
        return payload[key]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def _next_cursor(payload: dict) -> str | None:
    """Extract the ``cursor`` query param from a payload's ``next`` URL, if any."""
    from urllib.parse import parse_qs, urlsplit

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    nxt = data.get("next") if isinstance(data, dict) else None
    if not isinstance(nxt, str) or not nxt:
        return None
    return (parse_qs(urlsplit(nxt).query).get("cursor") or [None])[0]


def make_broker_client(settings: Settings, oauth_provider: Any) -> BrokerClient:
    import httpx
    from mcp.client.streamable_http import streamable_http_client
    from strands.tools.mcp import MCPClient

    def transport():
        http = httpx.AsyncClient(auth=oauth_provider, follow_redirects=True)
        return streamable_http_client(settings.robinhood_mcp_url, http_client=http)

    # startup_timeout must cover an interactive OAuth consent on the first run; Strands'
    # 30s default is too short for browser approval + 2FA + paste (silent refresh is fast).
    return BrokerClient(MCPClient(transport, startup_timeout=settings.mcp_startup_timeout))
