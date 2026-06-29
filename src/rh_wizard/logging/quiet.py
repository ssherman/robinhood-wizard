"""Quiet noisy third-party request logs so they never bury an interactive prompt.

``cli/app.py`` calls ``logging.basicConfig(level=INFO)``, which otherwise lets httpx/openai/mcp
log every HTTP request at INFO — that output scrolls over the human-approval confirmation prompt
(``Type 'yes' to place these orders``). Clamp those libraries (and their children) to WARNING;
our own loggers and any real warnings/errors are unaffected.
"""

from __future__ import annotations

import logging

_NOISY = ("httpx", "httpcore", "openai", "mcp")


def quiet_dependency_logs(level: int = logging.WARNING) -> None:
    """Clamp the noisy dependency loggers (and their children) to ``level``."""
    for name in _NOISY:
        logging.getLogger(name).setLevel(level)
