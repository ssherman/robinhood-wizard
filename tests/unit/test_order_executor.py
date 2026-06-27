import os
from decimal import Decimal

import pytest

from rh_wizard.execution.base import OrderExecutor
from rh_wizard.execution.robinhood import RobinhoodOrderExecutor, _order_params
from rh_wizard.models.plan import TradeIntent


def test_order_params_whole_share_is_limit():
    intent = TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190")
    order_type, params = _order_params(intent)
    assert order_type == "limit"
    assert params == {"quantity": "3", "limit_price": "190"}


def test_order_params_fractional_buy_is_market_notional():
    intent = TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99")
    order_type, params = _order_params(intent)
    assert order_type == "market"
    assert params == {"dollar_amount": "180.00"}  # no limit price on a market order


def test_order_params_fractional_sell_is_market_quantity():
    intent = TradeIntent(side="sell", symbol="NVDA", quantity="1.5", limit_price="100")
    order_type, params = _order_params(intent)
    assert order_type == "market"
    assert params == {"quantity": "1.5"}


def test_order_params_whole_sell_is_limit():
    intent = TradeIntent(side="sell", symbol="NVDA", quantity="2", limit_price="100")
    order_type, params = _order_params(intent)
    assert order_type == "limit"
    assert params == {"quantity": "2", "limit_price": "100"}


class FakeBroker:
    def __init__(self):
        self.placed = []

    def review_equity_order(self, account_number, symbol, side, order_type, **kw):
        return {"data": {"estimated_cost": "570.00", "alerts": []}}

    def place_equity_order(self, account_number, symbol, side, order_type, *, ref_id=None, **kw):
        self.placed.append((symbol, order_type, ref_id, kw))
        return {"data": {"id": "ord-123", "state": "confirmed"}}


def test_review_ok_when_no_alerts():
    ex = RobinhoodOrderExecutor(FakeBroker())
    rv = ex.review(TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1")
    assert rv.ok is True
    assert rv.estimated_cost == Decimal("570.00")


def test_review_blocks_on_alerts():
    class AlertBroker(FakeBroker):
        def review_equity_order(self, *a, **k):
            return {"data": {"alerts": ["insufficient buying power"]}}

    ex = RobinhoodOrderExecutor(AlertBroker())
    rv = ex.review(TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1")
    assert rv.ok is False
    assert "insufficient buying power" in rv.alerts


def test_place_returns_placed_orderresult_with_ref_id():
    broker = FakeBroker()
    ex = RobinhoodOrderExecutor(broker)
    intent = TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99")
    out = ex.place(intent, "ACC1", "ref-1")
    assert out.status == "placed"
    assert out.order_id == "ord-123"
    assert out.ref_id == "ref-1"
    assert broker.placed[0][2] == "ref-1"  # ref_id forwarded


def test_place_failure_returns_failed_orderresult():
    class BoomBroker(FakeBroker):
        def place_equity_order(self, *a, **k):
            raise RuntimeError("gateway 500")

    ex = RobinhoodOrderExecutor(BoomBroker())
    intent = TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190")
    out = ex.place(intent, "ACC1", "r")
    assert out.status == "failed"
    assert "gateway 500" in str(out.raw)


def test_satisfies_executor_protocol():
    assert isinstance(RobinhoodOrderExecutor(FakeBroker()), OrderExecutor)


def test_order_params_raises_on_unsizeable_intent():
    intent = TradeIntent(side="buy", symbol="X", limit_price="100")  # no amount, no quantity
    with pytest.raises(ValueError):
        _order_params(intent)


def test_place_malformed_intent_returns_failed_not_raises():
    # A malformed (unsizeable) intent must NOT raise out of place — it returns failed.
    ex = RobinhoodOrderExecutor(FakeBroker())
    intent = TradeIntent(side="buy", symbol="X", limit_price="100")  # unsizeable
    out = ex.place(intent, "ACC1", "r")
    assert out.status == "failed"


def test_review_broker_exception_blocks():
    class BoomReviewBroker(FakeBroker):
        def review_equity_order(self, *a, **k):
            raise RuntimeError("review 500")

    rv = RobinhoodOrderExecutor(BoomReviewBroker()).review(
        TradeIntent(side="buy", symbol="AAPL", quantity="3", limit_price="190"), "ACC1"
    )
    assert rv.ok is False
    assert any("review 500" in a for a in rv.alerts)


@pytest.mark.skipif(
    not (os.environ.get("RH_WIZARD_LIVE") and os.environ.get("RH_WIZARD_LIVE_EXECUTE")),
    reason="live review test: needs RH_WIZARD_LIVE=1 and RH_WIZARD_LIVE_EXECUTE=1 + a cached token",
)
def test_live_review_only_never_places(monkeypatch):
    # REVIEW ONLY — this test never calls place_equity_order.
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.memory.portfolio import resolve_account_number
    from rh_wizard.models.plan import TradeIntent

    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        account = resolve_account_number(broker, settings)
        ex = RobinhoodOrderExecutor(broker)
        intent = TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="1.00")
        rv = ex.review(intent, account)
        assert isinstance(rv.ok, bool)  # a ReviewResult came back; we never place
