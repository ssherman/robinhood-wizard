from decimal import Decimal

from rh_wizard.models.order import OrderResult, ReviewResult


def test_review_result_defaults():
    r = ReviewResult(ok=True)
    assert r.ok is True
    assert r.estimated_cost is None
    assert r.alerts == []
    assert r.raw == {}


def test_review_result_blocking():
    r = ReviewResult(ok=False, alerts=["insufficient buying power"], estimated_cost=Decimal("100"))
    assert r.ok is False
    assert r.alerts == ["insufficient buying power"]


def test_order_result_placed():
    o = OrderResult(
        symbol="AAPL",
        side="buy",
        status="placed",
        order_type="limit",
        quantity=Decimal("3"),
        limit_price=Decimal("190"),
        order_id="ord-1",
        ref_id="ref-1",
    )
    assert o.status == "placed"
    assert o.order_id == "ord-1"
    assert o.quantity == Decimal("3")


def test_order_result_skipped_minimal():
    o = OrderResult(symbol="MU", side="buy", status="skipped", amount=Decimal("180"))
    assert o.status == "skipped"
    assert o.order_type == ""  # default; never placed
    assert o.order_id is None
    assert o.ref_id == ""
