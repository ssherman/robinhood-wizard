"""Suppress one benign MCP SDK warning without hiding real ones.

On context exit the mcp Streamable-HTTP client logs
``WARNING "Session termination failed: <status>"`` (Robinhood's terminate endpoint
returns 400). It is cosmetic. We drop exactly that message on that logger and let every
other record through.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "mcp.client.streamable_http"


class _SessionTerminationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Session termination failed")


def silence_session_termination_warning() -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not any(isinstance(f, _SessionTerminationFilter) for f in logger.filters):
        logger.addFilter(_SessionTerminationFilter())
