"""User-facing rendering helpers (terminal output) built on rich."""

from __future__ import annotations

from rh_wizard.masking import mask_account


def render_to_str(renderable, width: int = 100) -> str:
    """Render any rich renderable (or plain string) to text — for echo and for tests."""
    import io

    from rich.console import Console

    buf = io.StringIO()
    Console(file=buf, width=width, no_color=True).print(renderable)
    return buf.getvalue()


def fmt_money(value) -> str:
    return "-" if value is None else f"${value:,.2f}"


def fmt_pct(value) -> str:
    return "-" if value is None else f"{value:,.2f}%"


def fmt_num(value) -> str:
    return "-" if value is None else str(value)


def render_positions(state) -> str:
    """Render a PortfolioState as a table plus a summary line."""
    from rich.table import Table

    table = Table(title=f"Positions — account {mask_account(state.account_number)}")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("Unrealized P/L", justify="right")
    table.add_column("%", justify="right")
    for p in state.positions:
        table.add_row(
            p.symbol,
            fmt_num(p.quantity),
            fmt_money(p.average_cost),
            fmt_money(p.current_price),
            fmt_money(p.market_value),
            fmt_money(p.unrealized_pl),
            fmt_pct(p.unrealized_pl_pct),
        )
    summary = (
        f"Cash: {fmt_money(state.cash)}   "
        f"Buying power: {fmt_money(state.buying_power)}   "
        f"Total value: {fmt_money(state.total_value)}   "
        f"Total return: {fmt_pct(state.total_return_pct)}"
    )
    body = render_to_str(table) if state.positions else "No open positions.\n"
    return body + summary


def render_history(trades) -> str:
    """Render a list of TradeRecords as a table (newest first)."""
    if not trades:
        return "No order history yet."

    from rich.table import Table

    table = Table(title="Order history")
    table.add_column("Date")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("State")
    table.add_column("Source")
    for t in trades:
        table.add_row(
            t.created_at,
            t.symbol,
            t.side,
            fmt_num(t.quantity),
            fmt_money(t.price),
            t.state,
            t.source or "-",
        )
    return render_to_str(table)


def render_market_context(context) -> str:
    """Render a MarketContext as a table plus any unmet-signal / note lines."""
    from rich.table import Table

    table = Table(title="Market data")
    table.add_column("Symbol")
    table.add_column("Price", justify="right")
    table.add_column("Avg Vol", justify="right")
    table.add_column("Mkt Cap", justify="right")
    table.add_column("P/E", justify="right")
    table.add_column("Sector")
    for sym, d in context.symbols.items():
        table.add_row(
            sym,
            fmt_money(d.price),
            fmt_num(d.average_volume),
            fmt_money(d.market_cap),
            fmt_num(d.pe_ratio),
            d.sector or "-",
        )
    body = render_to_str(table) if context.symbols else "No symbols.\n"
    if context.unmet_signals:
        body += "Unmet signals: " + ", ".join(s.value for s in context.unmet_signals) + "\n"
    for note in context.notes:
        body += f"Note: {note}\n"
    return body


def render_cycle_result(result) -> str:
    """Render a CycleResult (run header + portfolio + research + data gaps + vetted plan)."""
    from rich.table import Table

    run = result.run
    header = f"Run {run.run_id} — strategy '{run.strategy_id}' — mode {run.mode} — {run.status}"
    if run.status != "completed":
        return f"{header}\nABORTED: {run.note}\n"

    lines = [header]
    if result.portfolio is not None:
        p = result.portfolio
        lines.append(f"Cash: {fmt_money(p.cash)}   Total value: {fmt_money(p.total_value)}")
    if result.report is not None and result.report.summary:
        lines.append(f"Research: {result.report.summary}")
    if result.report is not None and result.report.sources:
        lines.append("Sources:")
        for s in result.report.sources:
            label = s.title or s.url
            lines.append(f"  - {label} ({s.url})")

    # Surface data-resolution gaps so a partial-data run is visible to the operator (spec §13).
    if result.market is not None:
        if result.market.unmet_signals:
            unmet = ", ".join(s.value for s in result.market.unmet_signals)
            lines.append(f"Unmet signals: {unmet}")
        for note in result.market.notes:
            lines.append(f"Data note: {note}")

    vetted = result.vetted
    if vetted is not None and vetted.approved:
        table = Table(title="Proposed trades (DryRun — approved)")
        table.add_column("Side")
        table.add_column("Symbol")
        table.add_column("Qty", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Rationale")
        for i in vetted.approved:
            table.add_row(
                i.side, i.symbol, fmt_num(i.quantity), fmt_money(i.limit_price), i.rationale or "-"
            )
        lines.append(render_to_str(table).rstrip("\n"))

    if vetted is not None and vetted.rejected:
        lines.append("Rejected:")
        for r in vetted.rejected:
            lines.append(f"  {r.intent.side} {r.intent.symbol}: {r.reason}")

    if vetted is None or (not vetted.approved and not vetted.rejected):
        lines.append("No trades proposed.")

    lines.append("DryRun — no orders placed.")
    return "\n".join(lines) + "\n"
