from typer.testing import CliRunner

from rh_wizard.cli import auth
from rh_wizard.cli.app import app

runner = CliRunner()


class FakeBroker:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "190.00"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        return [
            {
                "symbol": s,
                "average_volume": "50000000",
                "market_cap": "3000000000000",
                "pe_ratio": "30",
                "sector": "Technology",
            }
            for s in symbols
        ]

    def get_equity_tradability(self, symbols):
        return [{"symbol": s, "fractional_tradability": "tradable"} for s in symbols]


def test_data_command_renders_resolved_market_data(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))  # isolate from real config
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["data", "aapl"])
    assert result.exit_code == 0
    assert "AAPL" in result.output  # upper-cased
    assert "$190.00" in result.output  # price
    assert "Technology" in result.output  # sector


def test_data_command_uppercases_symbol(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["data", "msft"])
    assert result.exit_code == 0
    assert "MSFT" in result.output
