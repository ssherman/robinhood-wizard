"""Compose the effective RiskPolicy: strategy overrides merged onto global defaults,
then clamped to an optional global hard-ceiling (spec §9).

Pure functions — no I/O, no config import. Callers pass the defaults/ceiling in.
"""

from __future__ import annotations

from collections.abc import Mapping

from rh_wizard.models.risk import RiskPolicy


def effective_policy(
    defaults: RiskPolicy, overrides: Mapping[str, object] | None = None
) -> RiskPolicy:
    """Layer ``overrides`` onto ``defaults``. Re-validates types and rejects unknown keys
    (RiskPolicy is ``extra="forbid"``)."""
    if not overrides:
        return defaults
    return RiskPolicy(**{**defaults.model_dump(), **dict(overrides)})
