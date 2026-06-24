import pytest

from rh_wizard.config.settings import Settings, load_settings


def test_defaults_when_no_file(tmp_path):
    s = load_settings(tmp_path / "missing.yaml")
    assert s.robinhood_mcp_url == "https://agent.robinhood.com/mcp/trading"
    assert s.model_provider == "openai"
    assert s.oauth_redirect_port == 3030


def test_file_overrides_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model_provider: bedrock\nmodel_id: claude-opus-4-8\noauth_redirect_port: 4040\n"
    )
    s = load_settings(cfg)
    assert s.model_provider == "bedrock"
    assert s.model_id == "claude-opus-4-8"
    assert s.oauth_redirect_port == 4040
    # untouched fields keep defaults
    assert s.robinhood_mcp_url == "https://agent.robinhood.com/mcp/trading"


def test_unknown_key_rejected(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("bogus_key: 1\n")
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_settings_is_constructible_with_no_args():
    assert isinstance(Settings(), Settings)
