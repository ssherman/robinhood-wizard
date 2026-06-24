# tests/unit/test_models_market_context.py
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData, SymbolRisk
from rh_wizard.models.signals import Signal  # noqa: F401


def test_symbol_data_defaults_are_none():
    d = SymbolData(symbol="AAPL")
    assert d.price is None
    assert d.market_cap is None
    assert d.sector is None


def test_symbol_data_coerces_decimals():
    d = SymbolData(symbol="AAPL", price="190.50", market_cap="3.0E12")
    assert d.price == Decimal("190.50")
    assert d.market_cap == Decimal("3.0E12")


def test_market_context_defaults_empty():
    ctx = MarketContext()
    assert ctx.symbols == {}
    assert ctx.requested == []
    assert ctx.unmet_signals == []
    assert ctx.notes == []


def test_to_symbol_risk_includes_only_priced_symbols():
    ctx = MarketContext(
        symbols={
            "AAPL": SymbolData(
                symbol="AAPL", price="190", average_volume="50000000", market_cap="3.0E12"
            ),
            "ZZZZ": SymbolData(symbol="ZZZZ"),  # no price -> excluded
        }
    )
    risk = ctx.to_symbol_risk()
    assert set(risk) == {"AAPL"}
    assert isinstance(risk["AAPL"], SymbolRisk)
    assert risk["AAPL"].price == Decimal("190")
    assert risk["AAPL"].average_volume == Decimal("50000000")
    assert risk["AAPL"].market_cap == Decimal("3.0E12")


def test_to_symbol_risk_passes_through_missing_volume_and_cap():
    ctx = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})
    risk = ctx.to_symbol_risk()
    assert risk["AAPL"].average_volume is None
    assert risk["AAPL"].market_cap is None
