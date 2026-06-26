from rh_wizard.allocation.base import BucketRecommender
from rh_wizard.allocation.web_llm import RECOMMEND_SYSTEM, WebBucketRecommender
from rh_wizard.models.allocation import (
    AllocationRecommendation,
    BucketRecommendation,
    RecommendedPosition,
)
from rh_wizard.models.bucket import Bucket
from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Source
from rh_wizard.models.strategy import Strategy


class FakeWebSearchLlm:
    def __init__(self, rec):
        self._rec = rec
        self.last_model = None
        self.last_prompt = None
        self.last_system = None

    def research(self, output_model, prompt, system=""):
        self.last_model = output_model
        self.last_prompt = prompt
        self.last_system = system
        return self._rec, [Source(title="s", url="https://e/x")]


def _market():
    return MarketContext(symbols={"NVDA": SymbolData(symbol="NVDA", price="100")})


def _portfolio():
    return PortfolioState(account_number="A", positions=[], cash="1000", buying_power="1000")


def test_recommend_maps_and_attaches_sources():
    rec = AllocationRecommendation(
        buckets=[
            BucketRecommendation(
                bucket_id="ai", positions=[RecommendedPosition(symbol="NVDA", weight="100")]
            )
        ]
    )
    fake = FakeWebSearchLlm(rec)
    strat = Strategy(
        id="t", name="T", buckets=[Bucket(id="ai", target_pct="100", intent="ai leaders")]
    )
    out = WebBucketRecommender(fake).recommend(strat, {"ai": ["NVDA"]}, _market(), _portfolio())
    assert out.buckets[0].positions[0].symbol == "NVDA"
    assert [s.url for s in out.sources] == ["https://e/x"]
    assert fake.last_model is AllocationRecommendation
    assert fake.last_system == RECOMMEND_SYSTEM
    assert "ai leaders" in fake.last_prompt
    assert "NVDA" in fake.last_prompt


def test_satisfies_recommender_protocol():
    fake = FakeWebSearchLlm(AllocationRecommendation())
    assert isinstance(WebBucketRecommender(fake), BucketRecommender)
