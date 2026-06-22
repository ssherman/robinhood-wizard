"""User-facing rendering helpers (terminal output).

``mask_account`` is presentation masking — it shows only the last few characters of an
account number, per the Robinhood tool guide. This is separate from
``rh_wizard.logging.redaction`` (which scrubs secrets from logs).
"""

from __future__ import annotations


def mask_account(value: str, visible: int = 4) -> str:
    s = str(value)
    if len(s) <= visible:
        return s
    return "*" * (len(s) - visible) + s[-visible:]


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
