import io

from rh_wizard.cli.approval import CliApprovalGate
from rh_wizard.execution.base import ApprovalGate
from rh_wizard.models.plan import TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState


def _vetted():
    return VettedPlan(
        approved=[
            TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"),
            TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99"),
        ]
    )


def _portfolio():
    return PortfolioState(
        account_number="ACC1234567890", positions=[], cash="3000", buying_power="3000"
    )


def test_confirm_true_only_on_exact_yes(capsys):
    gate = CliApprovalGate(stdin=io.StringIO("yes\n"))
    assert gate.confirm(_vetted(), _portfolio(), "ACC1234567890") is True
    out = capsys.readouterr().out
    assert "AAPL" in out and "MU" in out  # orders listed
    assert "7890" in out and "ACC1234567890" not in out  # account masked
    assert "$570.00" in out or "570" in out  # est. cost shown (3 * 190)


def test_confirm_false_on_anything_else(capsys):
    acc = "ACC1234567890"
    assert CliApprovalGate(stdin=io.StringIO("y\n")).confirm(_vetted(), _portfolio(), acc) is False
    assert CliApprovalGate(stdin=io.StringIO("\n")).confirm(_vetted(), _portfolio(), acc) is False
    assert CliApprovalGate(stdin=io.StringIO("no\n")).confirm(_vetted(), _portfolio(), acc) is False
    assert (
        CliApprovalGate(stdin=io.StringIO("YES\n")).confirm(_vetted(), _portfolio(), acc) is False
    )


def test_satisfies_approval_protocol():
    assert isinstance(CliApprovalGate(), ApprovalGate)


def test_confirm_shows_actual_order_kind(capsys):
    vetted = VettedPlan(
        approved=[
            TradeIntent(
                side="buy", symbol="AAPL", quantity="3", limit_price="190"
            ),  # whole -> limit
            TradeIntent(
                side="buy", symbol="MU", amount="180.00", limit_price="1122.99"
            ),  # fractional buy -> market
            TradeIntent(
                side="sell", symbol="NVDA", quantity="1.5", limit_price="100"
            ),  # fractional sell -> market
        ]
    )
    CliApprovalGate(stdin=io.StringIO("yes\n")).confirm(vetted, _portfolio(), "ACC1234567890")
    lines = capsys.readouterr().out.splitlines()
    aapl = next(line for line in lines if "AAPL" in line)
    mu = next(line for line in lines if "MU" in line)
    nvda = next(line for line in lines if "NVDA" in line)
    assert "limit" in aapl
    assert "market" in mu  # fractional buy is a market order
    assert "market" in nvda  # fractional sell is a market order (NOT limit)
