from rh_wizard.discovery.base import UniverseDiscoverer
from rh_wizard.discovery.web_llm import DISCOVERY_SYSTEM, WebUniverseDiscoverer
from rh_wizard.models.compile import SuggestedTicker
from rh_wizard.models.discovery import DiscoveredUniverse
from rh_wizard.models.research import Source
from rh_wizard.models.strategy import Strategy


class FakeWebSearchLlm:
    def __init__(self, tickers):
        self._tickers = tickers
        self.last_model = None
        self.last_prompt = None
        self.last_system = None

    def research(self, output_model, prompt, system=""):
        self.last_model = output_model
        self.last_prompt = prompt
        self.last_system = system
        return output_model(tickers=self._tickers), [Source(title="s", url="https://e/x")]


def test_discover_maps_normalizes_and_attaches_sources():
    fake = FakeWebSearchLlm([SuggestedTicker(symbol=" nvda ", rationale="ai")])
    result = WebUniverseDiscoverer(fake).discover(Strategy(id="m", name="M", intent="large-cap ai"))
    assert [t.symbol for t in result.tickers] == ["NVDA"]  # stripped + uppercased
    assert [s.url for s in result.sources] == ["https://e/x"]
    assert fake.last_model is DiscoveredUniverse
    assert fake.last_system == DISCOVERY_SYSTEM
    assert "large-cap ai" in fake.last_prompt


def test_discover_dedupes_and_caps_to_max_candidates():
    fake = FakeWebSearchLlm(
        [
            SuggestedTicker(symbol="NVDA"),
            SuggestedTicker(symbol="nvda"),  # dup after normalize
            SuggestedTicker(symbol="MSFT"),
            SuggestedTicker(symbol="META"),
        ]
    )
    result = WebUniverseDiscoverer(fake).discover(
        Strategy(id="m", name="M", intent="ai", max_candidates=2)
    )
    assert [t.symbol for t in result.tickers] == ["NVDA", "MSFT"]  # deduped, capped at 2


def test_discover_drops_blank_symbols():
    fake = FakeWebSearchLlm([SuggestedTicker(symbol="  "), SuggestedTicker(symbol="NVDA")])
    result = WebUniverseDiscoverer(fake).discover(Strategy(id="m", name="M", intent="ai"))
    assert [t.symbol for t in result.tickers] == ["NVDA"]


def test_satisfies_discoverer_protocol():
    assert isinstance(WebUniverseDiscoverer(FakeWebSearchLlm([])), UniverseDiscoverer)
