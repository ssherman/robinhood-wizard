from decimal import Decimal

import pydantic
import pytest

from rh_wizard.models.bucket import Bucket
from rh_wizard.models.strategy import Strategy


def test_bucket_minimal_defaults():
    b = Bucket(id="ai", target_pct="40")
    assert b.id == "ai"
    assert b.name == ""
    assert b.target_pct == Decimal("40")
    assert b.universe == []
    assert b.discover is False
    assert b.max_candidates == 20


def test_bucket_forbids_unknown_fields():
    with pytest.raises(pydantic.ValidationError):
        Bucket(id="ai", target_pct="40", bogus=1)


def test_strategy_bucketed_defaults():
    s = Strategy(
        id="thematic",
        name="Thematic",
        buckets=[Bucket(id="ai", target_pct="40"), Bucket(id="energy", target_pct="20")],
    )
    assert [b.id for b in s.buckets] == ["ai", "energy"]
    assert s.allow_fractional is True
    assert s.rebalance_mode == "full"
    assert s.rebalance_band_pct == Decimal("5")


def test_strategy_rejects_targets_over_100():
    with pytest.raises(pydantic.ValidationError):
        Strategy(
            id="m",
            name="M",
            buckets=[Bucket(id="a", target_pct="70"), Bucket(id="b", target_pct="40")],
        )


def test_strategy_rejects_non_positive_target():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", buckets=[Bucket(id="a", target_pct="0")])


def test_strategy_rejects_unknown_rebalance_mode():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", buckets=[Bucket(id="a", target_pct="40")], rebalance_mode="wild")


def test_strategy_rejects_mixing_buckets_with_flat_universe():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", universe=["AAPL"], buckets=[Bucket(id="a", target_pct="40")])


def test_strategy_rejects_mixing_buckets_with_flat_discover():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", discover=True, buckets=[Bucket(id="a", target_pct="40")])


def test_flat_strategy_still_valid():
    s = Strategy(id="m", name="M", universe=["AAPL"], discover=True)
    assert s.buckets == []
    assert s.allow_fractional is True
