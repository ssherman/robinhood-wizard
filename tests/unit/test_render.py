from decimal import Decimal

from rh_wizard.cli.render import fmt_money, fmt_num, fmt_pct, render_cycle_result, render_to_str
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.research import ResearchReport, Source


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


class _Result:
    def __init__(self, report):
        self.run = CycleRun(
            run_id="r1",
            strategy_id="m",
            mode="dryrun",
            started_at="t",
            finished_at="t",
            status="completed",
        )
        self.portfolio = None
        self.market = None
        self.report = report
        self.plan = None
        self.vetted = None


def test_render_shows_sources():
    report = ResearchReport(summary="ok", sources=[Source(title="Headline", url="https://x/y")])
    out = render_cycle_result(_Result(report))
    assert "Sources:" in out
    assert "Headline" in out
    assert "https://x/y" in out
