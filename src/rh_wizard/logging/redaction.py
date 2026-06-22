"""Scrub secret-shaped values from log output so logs are safe to share."""

from __future__ import annotations

import logging
import re

_MASK = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    # Bearer tokens
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    # JSON-ish "...token": "value"
    re.compile(
        r'("(?:access_token|refresh_token|token|client_secret)"\s*:\s*")[^"]+(")',
        re.IGNORECASE,
    ),
    # Long digit runs (account numbers, ids) — 11+ digits
    re.compile(r"\b\d{11,}\b"),
]


def redact(text: str) -> str:
    out = text
    out = _PATTERNS[0].sub(rf"\1{_MASK}", out)
    out = _PATTERNS[1].sub(rf"\1{_MASK}\2", out)
    out = _PATTERNS[2].sub(_MASK, out)
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_redaction(logger: logging.Logger | None = None) -> None:
    target = logger if logger is not None else logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in target.filters):
        target.addFilter(RedactingFilter())
