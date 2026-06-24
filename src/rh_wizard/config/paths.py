"""Filesystem locations for Robinhood Wizard runtime state.

All runtime state lives under a single home directory (default ``~/.rh-wizard``),
overridable with the ``RH_WIZARD_HOME`` env var (used by tests and power users).
"""

from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    override = os.environ.get("RH_WIZARD_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".rh-wizard"


def config_path() -> Path:
    return home_dir() / "config.yaml"


def tokens_path() -> Path:
    return home_dir() / "tokens.json"


def db_path() -> Path:
    return home_dir() / "wizard.db"


def strategies_dir() -> Path:
    return home_dir() / "strategies"


def ensure_home() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir's mode is subject to umask; enforce explicitly.
    d.chmod(0o700)
    return d
