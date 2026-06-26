"""Global, user-editable configuration (loaded from ``~/.rh-wizard/config.yaml``)."""

from __future__ import annotations

from pathlib import Path

import pydantic
import yaml

from rh_wizard.config import paths
from rh_wizard.models.risk import RiskCeiling, RiskPolicy


class Settings(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    robinhood_mcp_url: str = "https://agent.robinhood.com/mcp/trading"
    # Seconds the MCP client waits for initialization. The default must comfortably exceed an
    # interactive OAuth consent (browser approval + 2FA + paste); Strands' own default of 30s
    # is far too short and aborts the first-time consent.
    mcp_startup_timeout: int = 300
    model_provider: str = "openai"
    model_id: str = "gpt-5.5"
    oauth_redirect_host: str = "localhost"
    oauth_redirect_port: int = 3030
    oauth_client_name: str = "Robinhood Wizard"
    # Optional: pin which brokerage account to trade in. Leave unset to auto-select the
    # single account, or (with several) the one flagged agentic_allowed=true.
    account_number: str | None = None
    risk: RiskPolicy = pydantic.Field(default_factory=RiskPolicy)
    risk_ceiling: RiskCeiling | None = None


def load_settings(path: Path | None = None) -> Settings:
    cfg_path = path if path is not None else paths.config_path()
    if not cfg_path.exists():
        return Settings()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    try:
        return Settings(**data)
    except pydantic.ValidationError as exc:
        raise ValueError(f"Invalid config at {cfg_path}: {exc}") from exc
