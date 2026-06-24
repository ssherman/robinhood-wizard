from decimal import Decimal

from rh_wizard.cli.render import fmt_money, fmt_num, fmt_pct, render_to_str


def test_render_to_str_outputs_text():
    from rich.table import Table

    table = Table()
    table.add_column("Symbol")
    table.add_row("AAPL")
    out = render_to_str(table)
    assert "AAPL" in out


def test_formatters_handle_none():
    assert fmt_money(None) == "-"
    assert fmt_pct(None) == "-"
    assert fmt_num(None) == "-"


def test_formatters_format_decimals():
    assert fmt_money(Decimal("1234.5")) == "$1,234.50"
    # 12.349 rounds unambiguously to 12.35 (avoid the half-even tie at .345).
    assert fmt_pct(Decimal("12.349")) == "12.35%"
    assert fmt_num(Decimal("10")) == "10"


def test_render_market_context_table_and_metadata_lines():
    from decimal import Decimal

    from rh_wizard.cli.render import render_market_context
    from rh_wizard.models.market import MarketContext, SymbolData
    from rh_wizard.models.signals import Signal

    ctx = MarketContext(
        symbols={"AAPL": SymbolData(symbol="AAPL", price=Decimal("190"), sector="Technology")},
        unmet_signals=[Signal.EARNINGS],
        notes=["robinhood fetch failed: boom"],
    )
    out = render_market_context(ctx)
    assert "AAPL" in out
    assert "$190.00" in out
    assert "Technology" in out
    assert "Unmet signals: earnings" in out  # Signal.EARNINGS.value
    assert "robinhood fetch failed: boom" in out  # note line


def test_render_market_context_empty_symbols():
    from rh_wizard.cli.render import render_market_context
    from rh_wizard.models.market import MarketContext

    assert "No symbols." in render_market_context(MarketContext())
