from typer.testing import CliRunner

from rh_wizard.cli import auth
from rh_wizard.cli import run as run_module
from rh_wizard.cli.app import app
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.research import Candidate, ResearchReport

runner = CliRunner()


class FakeStructuredLlm:
    def generate(self, output_model, prompt, system=""):
        if output_model is ResearchReport:
            return ResearchReport(candidates=[Candidate(symbol="AAPL", thesis="fit")], summary="ok")
        if output_model is TradePlan:
            return TradePlan(
                intents=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="100")],
                rationale="probe",
            )
        raise AssertionError(f"unexpected output_model {output_model}")


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
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    result = runner.invoke(app, ["run", "demo"])
    assert result.exit_code == 0
    assert "AAPL" in result.output  # LlmResearcher proposes AAPL; approved by risk engine
    assert "DryRun" in result.output
    assert "no orders" in result.output.lower()


def test_run_unknown_strategy_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["run", "ghost"])
    assert result.exit_code != 0
    assert "ghost" in result.output
