"""Presentation masking for account numbers (user-facing display).

Shows only the last few characters of an account number, per the Robinhood tool guide.
This is separate from ``rh_wizard.logging.redaction`` (which scrubs secrets from logs), and
is a neutral, dependency-free module so any layer (``cli``, ``memory``) can import it
without a layering inversion.
"""

from __future__ import annotations


def mask_account(value: str, visible: int = 4) -> str:
    s = str(value)
    if len(s) <= visible:
        return s
    return "*" * (len(s) - visible) + s[-visible:]
