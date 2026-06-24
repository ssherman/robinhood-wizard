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
        return [{"account_number": "ACC1", "agentic_allowed": True}]

    def get_equity_positions(self, account_number):
        return []

    def get_portfolio(self, account_number):
        return {"data": {"cash": "10000", "buying_power": "10000"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "100"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        return [
            {"symbol": s, "average_volume": "50000000", "market_cap": "3000000000000"}
            for s in symbols
        ]


def _write_strategy(home):
    d = home / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    (d / "demo.yaml").write_text(
        "id: demo\nname: Demo\nuniverse: [AAPL]\nsignals_needed: [price]\n"
    )


def test_strategies_lists_available(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    result = runner.invoke(app, ["strategies"])
    assert result.exit_code == 0
    assert "demo" in result.output


def test_run_executes_dryrun_cycle_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["run", "demo"])
    assert result.exit_code == 0
    assert "AAPL" in result.output  # 1-share probe buy proposed
    assert "DryRun" in result.output
    assert "no orders" in result.output.lower()


def test_run_unknown_strategy_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["run", "ghost"])
    assert result.exit_code != 0
    assert "ghost" in result.output
