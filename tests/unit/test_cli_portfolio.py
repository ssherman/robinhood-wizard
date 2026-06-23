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

    def get_equity_positions(self, account_number):
        return [{"symbol": "AAPL", "quantity": "10", "average_cost": "100"}]

    def get_portfolio(self, account_number):
        return {"data": {"cash": "500.00", "buying_power": "500.00"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": "AAPL", "last_trade_price": "120.00"}]


def test_positions_command_renders_and_masks(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))  # isolate from real config
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["positions"])
    assert result.exit_code == 0
    assert "AAPL" in result.output
    assert "$1,200.00" in result.output  # enriched market value
    assert "ACC123456" not in result.output  # account number masked
    assert "*****3456" in result.output
