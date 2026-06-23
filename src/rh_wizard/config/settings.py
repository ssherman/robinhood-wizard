"""Global, user-editable configuration (loaded from ``~/.rh-wizard/config.yaml``)."""

from __future__ import annotations

from pathlib import Path

import pydantic
import yaml

from rh_wizard.config import paths


class Settings(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    robinhood_mcp_url: str = "https://agent.robinhood.com/mcp/trading"
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-4-6"
    oauth_redirect_host: str = "localhost"
    oauth_redirect_port: int = 3030
    oauth_client_name: str = "Robinhood Wizard"
    # Optional: pin which brokerage account to trade in. Leave unset to auto-select the
    # single account, or (with several) the one flagged agentic_allowed=true.
    account_number: str | None = None


def load_settings(path: Path | None = None) -> Settings:
    cfg_path = path if path is not None else paths.config_path()
    if not cfg_path.exists():
        return Settings()
    data = yaml.safe_load(cfg_path.read_text()) or {}
    try:
        return Settings(**data)
    except pydantic.ValidationError as exc:
        raise ValueError(f"Invalid config at {cfg_path}: {exc}") from exc
