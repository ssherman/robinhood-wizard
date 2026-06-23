"""Live, opt-in shape verification for fundamentals against the real Robinhood MCP.

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_fundamentals.py -v -s

Prints the raw fundamentals keys and the resolved SymbolData so the parser can be pinned
to the confirmed field names (spec §18).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live fundamentals test",
)


def test_fundamentals_shape_live():
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource

    settings = load_settings()
    broker = auth._build_broker(settings)
    source = RobinhoodDataSource(broker)
    with broker:
        raw = broker.get_equity_fundamentals(["AAPL"])
        context = SignalResolver([source]).resolve(["AAPL", "MSFT"], source.provides())

    print("\nRaw fundamentals[0] keys:", sorted(raw[0].keys()) if raw else "none")
    for sym, d in context.symbols.items():
        print(
            f"{sym}: price={d.price} vol={d.average_volume} cap={d.market_cap} "
            f"pe={d.pe_ratio} pb={d.pb_ratio} sector={d.sector} industry={d.industry}"
        )
    print(f"Unmet: {context.unmet_signals}  Notes: {context.notes}")

    assert "AAPL" in context.symbols
    assert context.symbols["AAPL"].price is not None  # quotes path confirmed live in Phase 1
