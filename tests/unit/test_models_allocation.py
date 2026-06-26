from decimal import Decimal

from rh_wizard.models.allocation import (
    AllocationRecommendation,
    AllocationReport,
    BucketAllocation,
    BucketRecommendation,
    RecommendedPosition,
)
from rh_wizard.models.research import Source


def test_recommendation_holds_buckets_and_weights():
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai",
                positions=[
                    RecommendedPosition(symbol="NVDA", weight="50", thesis="leader"),
                    RecommendedPosition(symbol="MSFT", weight="50"),
                ],
            )
        ],
        summary="ok",
        sources=[Source(title="t", url="https://e/x")],
    )
    assert rec.buckets[0].positions[0].symbol == "NVDA"
    assert rec.buckets[0].positions[0].weight == Decimal("50")
    assert rec.sources[0].url == "https://e/x"


def test_recommended_position_weight_optional():
    p = RecommendedPosition(symbol="NVDA")
    assert p.weight is None


def test_allocation_report_defaults():
    r = AllocationReport(investable=Decimal("900"))
    assert r.buckets == []
    assert r.orphans == []
    assert r.investable == Decimal("900")


def test_bucket_allocation_fields():
    ba = BucketAllocation(
        bucket_id="ai",
        name="AI",
        target_pct=Decimal("40"),
        current_pct=Decimal("30"),
        drift_pct=Decimal("-10"),
        within_band=False,
        action="buy",
    )
    assert ba.action == "buy"
    assert ba.drift_pct == Decimal("-10")
