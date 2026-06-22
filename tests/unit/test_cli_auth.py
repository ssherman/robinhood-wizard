from typer.testing import CliRunner

from rh_wizard.cli import auth
from rh_wizard.cli.app import app

runner = CliRunner()


class FakeBroker:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_accounts(self):
        return [{"account_number": "AG-123", "type": "agentic"}]


def test_app_shows_disclaimer():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # "DISCLAIMER" is a single token — robust against rich help-text line wrapping.
    assert "DISCLAIMER" in result.output


def test_accounts_command_prints_accounts(monkeypatch):
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["accounts"])
    assert result.exit_code == 0
    assert "AG-123" in result.output


def test_accounts_command_never_prints_tokens(monkeypatch):
    class LeakyBroker(FakeBroker):
        def get_accounts(self):
            return [{"account_number": "AG-123", "secret": "Bearer abcdef12345"}]

    monkeypatch.setattr(auth, "_build_broker", lambda settings: LeakyBroker())
    result = runner.invoke(app, ["accounts"])
    assert "abcdef12345" not in result.output
