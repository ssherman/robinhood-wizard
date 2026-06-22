import stat

from rh_wizard.config import paths


def test_home_dir_defaults_to_dot_rh_wizard(monkeypatch):
    monkeypatch.delenv("RH_WIZARD_HOME", raising=False)
    assert paths.home_dir().name == ".rh-wizard"


def test_home_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path / "custom"))
    assert paths.home_dir() == tmp_path / "custom"


def test_derived_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.yaml"
    assert paths.tokens_path() == tmp_path / "tokens.json"
    assert paths.db_path() == tmp_path / "wizard.db"


def test_ensure_home_creates_dir_0700(monkeypatch, tmp_path):
    target = tmp_path / "home"
    monkeypatch.setenv("RH_WIZARD_HOME", str(target))
    result = paths.ensure_home()
    assert result.is_dir()
    assert stat.S_IMODE(result.stat().st_mode) == 0o700
