from decimal import Decimal

from rh_wizard.models.trade import TradeRecord


def test_trade_record_coerces_decimals():
    t = TradeRecord(
        order_id="O1",
        symbol="AAPL",
        side="buy",
        quantity="2",
        price="100.50",
        state="filled",
        created_at="2026-01-01T00:00:00Z",
    )
    assert t.quantity == Decimal("2")
    assert t.price == Decimal("100.50")
    assert t.source is None


def test_trade_record_allows_null_price():
    t = TradeRecord(
        order_id="O2",
        symbol="MSFT",
        side="sell",
        quantity="1",
        price=None,
        state="cancelled",
        created_at="2026-01-02",
    )
    assert t.price is None
