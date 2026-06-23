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
