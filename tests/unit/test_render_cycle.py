# tests/unit/test_render_cycle.py
from decimal import Decimal

from rh_wizard.cli.render import render_cycle_result
from rh_wizard.core.cycle import CycleResult
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.plan import RejectedIntent, TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.signals import Signal


def _run(status="completed", note=""):
    return CycleRun(
        run_id="abc123",
        strategy_id="momentum",
        mode="dryrun",
        started_at="2026-06-23T00:00:00",
        finished_at="2026-06-23T00:00:01",
        status=status,
        note=note,
    )


def test_render_approved_table_shows_amount_for_fractional_and_whole_buys():
    result = CycleResult(
        run=_run(),
        vetted=VettedPlan(
            approved=[
                # fractional buy: a notional dollar amount, no whole share quantity
                TradeIntent(side="buy", symbol="MU", amount="180.00", limit_price="1122.99"),
                # whole-share buy: amount derived as quantity * limit = 4 * 42.97 = 171.88
                TradeIntent(side="buy", symbol="SNY", quantity="4", limit_price="42.97"),
            ],
        ),
    )
    out = render_cycle_result(result)
    assert "Amount" in out  # new column header
    assert "$180.00" in out  # fractional buy's notional amount
    assert "$171.88" in out  # whole-share buy: 4 * 42.97
    assert "-" in out  # fractional buy still shows "-" for Qty


def test_render_completed_run_shows_plan_and_dryrun_footer():
    result = CycleResult(
        run=_run(),
        portfolio=PortfolioState(
            account_number="ACC1",
            positions=[],
            cash=Decimal("10000"),
            buying_power=Decimal("10000"),
            total_value=Decimal("10000"),
        ),
        report=ResearchReport(summary="(stub) 1 candidate"),
        vetted=VettedPlan(
            approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")],
            rejected=[
                RejectedIntent(
                    intent=TradeIntent(side="buy", symbol="NVDA", quantity="1", limit_price="1000"),
                    reason="would exceed max position",
                )
            ],
        ),
    )
    out = render_cycle_result(result)
    assert "momentum" in out
    assert "abc123" in out
    assert "AAPL" in out  # approved intent
    assert "NVDA" in out  # rejected intent
    assert "would exceed max position" in out
    assert "DryRun" in out  # footer
    assert "no orders" in out.lower()


def test_render_aborted_run_shows_reason():
    out = render_cycle_result(CycleResult(run=_run(status="aborted", note="reconcile failed: x")))
    assert "ABORTED" in out.upper()
    assert "reconcile failed: x" in out


def test_render_surfaces_unmet_signals_and_notes():
    from rh_wizard.models.market import MarketContext

    result = CycleResult(
        run=_run(),
        vetted=VettedPlan(
            approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")]
        ),
        market=MarketContext(
            unmet_signals=[Signal.EARNINGS], notes=["robinhood fetch failed: boom"]
        ),
    )
    out = render_cycle_result(result)
    assert "Unmet signals: earnings" in out  # Signal.EARNINGS.value
    assert "robinhood fetch failed: boom" in out  # degradation note surfaced


def test_render_no_trades_message_only_when_nothing_proposed():
    out = render_cycle_result(CycleResult(run=_run(), vetted=VettedPlan()))
    assert "No trades proposed." in out
    assert "DryRun" in out


def test_render_includes_allocation_block():
    from decimal import Decimal

    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.core.cycle import CycleResult
    from rh_wizard.models.allocation import (
        AllocationRecommendation,
        AllocationReport,
        BucketAllocation,
    )
    from rh_wizard.models.cycle import CycleRun
    from rh_wizard.models.plan import VettedPlan
    from rh_wizard.models.research import Source

    run = CycleRun(run_id="r1", strategy_id="b", mode="dryrun", started_at="t", status="completed")
    result = CycleResult(
        run=run,
        vetted=VettedPlan(),
        allocation=AllocationReport(
            buckets=[
                BucketAllocation(
                    bucket_id="ai",
                    name="AI",
                    target_pct=Decimal("40"),
                    current_pct=Decimal("30"),
                    drift_pct=Decimal("-10"),
                    within_band=False,
                    action="buy",
                )
            ],
            orphans=["TSLA"],
            investable=Decimal("900"),
        ),
        recommendation=AllocationRecommendation(sources=[Source(title="N", url="https://e/x")]),
    )
    out = render_cycle_result(result)
    assert "Allocation" in out
    assert "AI" in out and "buy" in out
    assert "TSLA" in out  # orphan listed
    assert "https://e/x" in out  # recommendation source
