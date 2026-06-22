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
