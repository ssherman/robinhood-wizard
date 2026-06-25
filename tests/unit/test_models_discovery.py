from rh_wizard.models.compile import SuggestedTicker
from rh_wizard.models.discovery import DiscoveredUniverse, DiscoveryResult
from rh_wizard.models.research import Source


def test_discovered_universe_holds_suggested_tickers():
    d = DiscoveredUniverse(tickers=[SuggestedTicker(symbol="NVDA", rationale="ai")])
    assert d.tickers[0].symbol == "NVDA"
    assert d.tickers[0].rationale == "ai"


def test_discovered_universe_defaults_empty():
    assert DiscoveredUniverse().tickers == []


def test_discovery_result_carries_tickers_and_sources():
    r = DiscoveryResult(
        tickers=[SuggestedTicker(symbol="NVDA")],
        sources=[Source(title="t", url="https://e/x")],
    )
    assert r.tickers[0].symbol == "NVDA"
    assert r.sources[0].url == "https://e/x"
