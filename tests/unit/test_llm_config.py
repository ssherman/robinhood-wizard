from rh_wizard.config.settings import Settings, load_settings


def test_settings_default_openai_provider():
    s = Settings()
    assert s.model_provider == "openai"
    assert s.model_id == "gpt-5.5"


def test_settings_model_overridable(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model_provider: anthropic\nmodel_id: claude-opus-4-8\n")
    s = load_settings(cfg)
    assert s.model_provider == "anthropic"
    assert s.model_id == "claude-opus-4-8"
