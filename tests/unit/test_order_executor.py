from decimal import Decimal

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
