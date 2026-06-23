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
