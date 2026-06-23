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
        return [{"account_number": "ACC123456", "type": "agentic"}]

    def get_equity_orders(self, account_number, *, created_at_gte=None):
        return [
            {
                "id": "O1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "2",
                "average_price": "100",
                "state": "filled",
                "created_at": "2026-01-01",
                "placed_agent": "agentic",
            }
        ]


def test_history_command_persists_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())

    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "AAPL" in result.output
    assert (tmp_path / "wizard.db").exists()

    # Re-running is idempotent and still renders.
    result2 = runner.invoke(app, ["history"])
    assert result2.exit_code == 0
    assert "AAPL" in result2.output


def test_history_command_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))

    class EmptyBroker(FakeBroker):
        def get_equity_orders(self, account_number, *, created_at_gte=None):
            return []

    monkeypatch.setattr(auth, "_build_broker", lambda settings: EmptyBroker())
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "No order history yet." in result.output
